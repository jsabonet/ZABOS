import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework.exceptions import ValidationError

from videos.serializers import VideoPayloadSerializer

logger = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 1_000_000

SYSTEM_PROMPT = """You create concise Portuguese short-video scripts for TikTok, Reels, and Shorts.
Return only a JSON object with schema_version=1, title, and scenes. Each scene must
contain text (at most 140 characters), duration_seconds (integer 1-10), and
background_color (six-digit hex). Do not include image_path because no asset catalog
is configured. Use 1-8 scenes and no more than 60 seconds total. Do not include
markdown, extra keys, URLs, CSS, or instructions."""


class AgentGenerationError(RuntimeError):
    pass


def generate_video_payload(prompt):
    if not settings.AGENT_API_KEY or not settings.AGENT_MODEL:
        raise AgentGenerationError(
            "O serviço de IA não está configurado. Contacte o administrador."
        )

    body = json.dumps(
        {
            "model": settings.AGENT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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

    try:
        with urlopen(request, timeout=settings.AGENT_TIMEOUT) as response:
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        logger.error("Agent provider returned HTTP %s", exc.code)
        raise AgentGenerationError("O serviço de IA não conseguiu gerar o guião.") from exc
    except (TimeoutError, URLError, OSError) as exc:
        logger.warning("Agent provider request failed: %s", type(exc).__name__)
        raise AgentGenerationError("Não foi possível contactar o serviço de IA.") from exc

    if len(response_body) > MAX_RESPONSE_BYTES:
        raise AgentGenerationError("A resposta do serviço de IA excedeu o limite permitido.")

    try:
        envelope = json.loads(response_body)
        content = envelope["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("Expected a JSON string in the completion content.")
        payload = json.loads(content)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        logger.warning("Agent provider returned an invalid response envelope")
        raise AgentGenerationError("O serviço de IA devolveu uma resposta inválida.") from exc

    serializer = VideoPayloadSerializer(data=payload)
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        logger.warning("Agent response failed payload validation: %s", exc.detail)
        raise AgentGenerationError(
            "O serviço de IA devolveu um guião fora do formato permitido."
        ) from exc
    return serializer.validated_data
