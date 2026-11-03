import json
import logging
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework.exceptions import ValidationError

from videos.serializers import VideoPayloadSerializer
from videos.video_templates import VIDEO_TEMPLATES
from videos.visual_themes import DEFAULT_VISUAL_THEME, VISUAL_THEMES

logger = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 1_000_000

SYSTEM_PROMPT = """You create concise Portuguese short-video scripts for TikTok, Reels, and Shorts.
Return only a JSON object with schema_version=2, title, visual_direction, scenes, and end_card.
visual_direction is one concise shared art-direction description (palette, lighting,
atmosphere, texture, and camera language) for the entire video. Each scene must
contain text (at most 140 characters), duration_seconds (positive integer),
background_color (six-digit hex), visual_prompt (an English image-generation prompt
of at most 600 characters), motion (slow_zoom, pan_left, pan_right, float, or none),
image_treatment (natural, warm, cool, monochrome, or film),
typography_animation (fade_up, pop, typewriter, word_reveal, or none), and
motion_graphic (none, accent_line, orbit, or corner_frame).
end_card must contain enabled (boolean), title (at most 100 characters), subtitle
(at most 180 characters), cta (at most 80 characters), and duration_seconds (1 to 10).
Keep the total scene duration plus an enabled end card at or below 60 seconds.
Visual intelligence requirements:
- Interpret the meaning and narrative purpose of the scene; do not turn topic keywords
  into generic search terms or a literal text depiction.
- Describe a specific subject performing an action in a meaningful environment, plus
  shot type, focal point, depth, and lighting.
- Use a distinct subject, visual metaphor, and framing in each adjacent scene while
  preserving the same shared visual_direction, palette, and photographic language.
- Keep prompts suitable for a vertical cinematic image and explicitly avoid words,
  captions, logos, watermarks, and UI text in generated imagery.
Do not invent image paths, asset IDs, audio files, or URLs. There is no fixed scene
count; use as many scenes as the requested content needs, but keep the sum of all
scene durations at or below 60 seconds. Use a 3-second enabled end card when the
scene duration is at most 57 seconds; otherwise disable it. The requested number of facts, tips, or items
may determine the number of scenes. Do not include markdown, extra keys, CSS, or React
code."""


class AgentGenerationError(RuntimeError):
    pass


def generate_video_payload(
    prompt,
    *,
    template_id="showcase",
    visual_theme_id=DEFAULT_VISUAL_THEME,
    generation_id=None,
    _validation_retry=False,
    _validation_errors=None,
):
    started_at = monotonic()
    if not settings.AGENT_API_KEY or not settings.AGENT_MODEL:
        logger.error(
            "generation_stage=agent_configuration_missing generation_id=%s",
            generation_id or "unknown",
        )
        raise AgentGenerationError(
            "O serviço de IA não está configurado. Contacte o administrador."
        )
    template = VIDEO_TEMPLATES.get(template_id)
    if template is None:
        raise AgentGenerationError("O formato de vídeo seleccionado não é válido.")
    visual_theme = VISUAL_THEMES.get(visual_theme_id)
    if visual_theme is None:
        raise AgentGenerationError("O tema visual seleccionado não é válido.")

    validation_instruction = ""
    if _validation_retry:
        validation_instruction = (
            "\n\nA resposta anterior não passou no contrato. Corrija estes erros e "
            "devolva um novo JSON completo, preservando o briefing: "
            f"{json.dumps(_validation_errors, ensure_ascii=False, default=str)}\n"
            "Não existe um máximo fixo de cenas, mas a soma das durações deve ser no "
            "máximo 60 segundos. Crie tantas cenas quantas o conteúdo exigir, "
            "distribuindo a duração total entre elas."
        )

    body = json.dumps(
        {
            "model": settings.AGENT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{SYSTEM_PROMPT}\n\n"
                        f"Formato seleccionado: {template['name']}.\n"
                        f"Objectivo: {template['purpose']}\n"
                        f"Estrutura narrativa: {template['structure']}\n"
                        "Aplique esta estrutura às cenas, mantendo o texto conciso.\n"
                        f"Tema visual: {visual_theme['name']}.\n"
                        f"Direcção visual do tema: {visual_theme['description']}\n"
                        f"Referência estética partilhada: {visual_theme['image_prompt_style']}\n"
                        "Mantenha uma identidade visual consistente entre cenas sem "
                        "repetir o mesmo enquadramento ou assunto."
                        f"{validation_instruction}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }
    ).encode("utf-8")
    request = Request(
        settings.AGENT_API_BASE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {settings.AGENT_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    logger.info(
        "generation_stage=agent_request_started generation_id=%s model=%s",
        generation_id or "unknown",
        settings.AGENT_MODEL,
    )
    try:
        with urlopen(request, timeout=settings.AGENT_TIMEOUT) as response:
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        logger.error(
            "generation_stage=agent_provider_http_error generation_id=%s "
            "http_status=%s duration_ms=%.2f",
            generation_id or "unknown",
            exc.code,
            (monotonic() - started_at) * 1000,
        )
        raise AgentGenerationError("O serviço de IA não conseguiu gerar o guião.") from exc
    except (TimeoutError, URLError, OSError) as exc:
        logger.warning(
            "generation_stage=agent_provider_connection_error generation_id=%s "
            "error_type=%s duration_ms=%.2f",
            generation_id or "unknown",
            type(exc).__name__,
            (monotonic() - started_at) * 1000,
        )
        raise AgentGenerationError("Não foi possível contactar o serviço de IA.") from exc

    if len(response_body) > MAX_RESPONSE_BYTES:
        logger.warning(
            "generation_stage=agent_response_too_large generation_id=%s "
            "response_bytes=%s",
            generation_id or "unknown",
            len(response_body),
        )
        raise AgentGenerationError("A resposta do serviço de IA excedeu o limite permitido.")

    try:
        envelope = json.loads(response_body)
        content = envelope["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("Expected a JSON string in the completion content.")
        payload = json.loads(content)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        logger.warning(
            "generation_stage=agent_response_invalid generation_id=%s "
            "error_type=%s",
            generation_id or "unknown",
            type(exc).__name__,
        )
        raise AgentGenerationError("O serviço de IA devolveu uma resposta inválida.") from exc

    if (
        isinstance(payload, dict)
        and "end_card" not in payload
        and isinstance(payload.get("scenes"), list)
    ):
        scene_duration = sum(
            scene.get("duration_seconds", 0)
            for scene in payload["scenes"]
            if isinstance(scene, dict)
            and isinstance(scene.get("duration_seconds", 0), int)
        )
        payload["end_card"] = {
            "enabled": scene_duration <= 57,
            "title": payload.get("title", "Obrigado por assistir")[:100],
            "subtitle": "Mais ideias para colocar em prática."[:180],
            "cta": "Segue para mais",
            "duration_seconds": 3,
        }

    serializer = VideoPayloadSerializer(data=payload)
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        logger.warning(
            "generation_stage=agent_payload_validation_failed generation_id=%s "
            "error_fields=%s",
            generation_id or "unknown",
            ",".join(sorted(exc.detail.keys()))
            if isinstance(exc.detail, dict)
            else "payload",
        )
        if not _validation_retry:
            logger.info(
                "generation_stage=agent_validation_retry generation_id=%s",
                generation_id or "unknown",
            )
            return generate_video_payload(
                prompt,
                template_id=template_id,
                visual_theme_id=visual_theme_id,
                generation_id=generation_id,
                _validation_retry=True,
                _validation_errors=exc.detail,
            )
        raise AgentGenerationError(
            "O serviço de IA devolveu um guião fora do formato permitido."
        ) from exc
    validated_payload = serializer.validated_data
    validated_payload["template_id"] = template_id
    logger.info(
        "generation_stage=agent_payload_validated generation_id=%s scenes=%s "
        "response_bytes=%s duration_ms=%.2f",
        generation_id or "unknown",
        len(validated_payload["scenes"]),
        len(response_body),
        (monotonic() - started_at) * 1000,
    )
    return validated_payload
