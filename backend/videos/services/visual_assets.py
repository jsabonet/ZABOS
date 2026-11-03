import logging
import secrets
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.files.base import ContentFile

from videos.models import MediaAsset
from videos.visual_themes import DEFAULT_VISUAL_THEME, VISUAL_THEMES

logger = logging.getLogger(__name__)

POLLINATIONS_IMAGE_URL = "https://gen.pollinations.ai/image/"
POLLINATIONS_IMAGE_MODEL = "black-forest-labs/flux.1-schnell"
IMAGE_TYPES = {
    "image/jpeg": (".jpg", lambda content: content.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda content: content.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": (
        ".webp",
        lambda content: content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    ),
}


class VisualAssetError(RuntimeError):
    pass


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


def _build_image_request(prompt, seed):
    if not isinstance(prompt, str) or not prompt.strip():
        raise VisualAssetError("A cena não tem uma descrição visual válida.")

    encoded_prompt = quote(prompt.strip(), safe="")
    params = urlencode(
        {
            "model": POLLINATIONS_IMAGE_MODEL,
            "width": 1080,
            "height": 1920,
            "seed": seed,
        }
    )
    headers = {
        "Accept": "image/jpeg,image/png,image/webp",
        "User-Agent": "LumeStudio/1.0",
    }
    if settings.POLLINATIONS_API_KEY:
        headers["Authorization"] = f"Bearer {settings.POLLINATIONS_API_KEY}"
    return Request(
        f"{POLLINATIONS_IMAGE_URL}{encoded_prompt}?{params}",
        headers=headers,
    )


def _generate_image(prompt, seed, *, generation_id=None, scene_index=None):
    started_at = monotonic()
    request = _build_image_request(prompt, seed)
    opener = build_opener(_NoRedirectHandler())
    logger.info(
        "generation_stage=image_provider_request_started generation_id=%s "
        "scene_index=%s",
        generation_id or "unknown",
        scene_index or "unknown",
    )
    try:
        with opener.open(request, timeout=settings.POLLINATIONS_TIMEOUT) as response:
            final_url = urlparse(response.geturl())
            if (
                final_url.scheme != "https"
                or final_url.hostname != "gen.pollinations.ai"
            ):
                raise VisualAssetError(
                    "O fornecedor devolveu um endereço de imagem inválido."
                )
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            image_data = response.read(settings.POLLINATIONS_MAX_IMAGE_BYTES + 1)
    except HTTPError as exc:
        logger.warning(
            "generation_stage=image_provider_http_error generation_id=%s "
            "scene_index=%s http_status=%s duration_ms=%.2f",
            generation_id or "unknown",
            scene_index or "unknown",
            exc.code,
            (monotonic() - started_at) * 1000,
        )
        raise VisualAssetError(
            "A geração automática de imagens não está disponível."
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        logger.warning(
            "generation_stage=image_provider_connection_error generation_id=%s "
            "scene_index=%s error_type=%s duration_ms=%.2f",
            generation_id or "unknown",
            scene_index or "unknown",
            type(exc).__name__,
            (monotonic() - started_at) * 1000,
        )
        raise VisualAssetError(
            "Não foi possível contactar o serviço de geração de imagens."
        ) from exc

    image_format = IMAGE_TYPES.get(content_type)
    if (
        image_format is None
        or len(image_data) > settings.POLLINATIONS_MAX_IMAGE_BYTES
        or not image_format[1](image_data)
    ):
        logger.warning(
            "generation_stage=image_provider_response_invalid "
            "generation_id=%s scene_index=%s content_type=%s "
            "response_bytes=%s",
            generation_id or "unknown",
            scene_index or "unknown",
            content_type,
            len(image_data),
        )
        raise VisualAssetError(
            "O fornecedor devolveu uma imagem num formato inválido ou acima do limite."
        )
    logger.info(
        "generation_stage=image_provider_response_received generation_id=%s "
        "scene_index=%s content_type=%s response_bytes=%s duration_ms=%.2f",
        generation_id or "unknown",
        scene_index or "unknown",
        content_type,
        len(image_data),
        (monotonic() - started_at) * 1000,
    )
    return image_format[0], image_data


def _save_generated_image(
    prompt,
    seed,
    user,
    *,
    generation_id=None,
    scene_index=None,
):
    extension, image_data = _generate_image(
        prompt,
        seed,
        generation_id=generation_id,
        scene_index=scene_index,
    )
    asset = MediaAsset(
        user=user,
        kind=MediaAsset.Kind.IMAGE,
        original_name=f"pollinations-{seed}{extension}",
        size_bytes=len(image_data),
        source_provider="pollinations",
        source_url="https://gen.pollinations.ai",
        generation_prompt=prompt,
        generation_seed=seed,
    )
    asset.file.save(
        asset.original_name,
        ContentFile(image_data),
        save=False,
    )
    try:
        asset.save()
    except Exception:
        asset.file.delete(save=False)
        raise
    return asset


def _next_seed(used_seeds):
    while True:
        seed = secrets.randbelow(2**31)
        if seed not in used_seeds:
            used_seeds.add(seed)
            return seed


def _compose_image_prompt(scene_prompt, visual_direction, visual_theme_id):
    theme = VISUAL_THEMES.get(visual_theme_id, VISUAL_THEMES[DEFAULT_VISUAL_THEME])
    shared_direction = visual_direction.strip() or theme["image_prompt_style"]
    return (
        f"Shared visual direction for this entire video: {shared_direction} "
        f"Scene-specific image: {scene_prompt.strip()} "
        "Keep the shared palette, lighting, and photographic language consistent, "
        "but use a distinct subject and framing for this scene. "
        "Vertical cinematic composition, no text, no logos, no watermark."
    )


def prepare_visual_assets(
    payload,
    user,
    *,
    visual_theme_id=DEFAULT_VISUAL_THEME,
    generation_id=None,
):
    scenes_needing_assets = [
        scene
        for scene in payload.get("scenes", [])
        if not scene.get("image_path") and not scene.get("layers")
    ]
    if not scenes_needing_assets:
        logger.info(
            "generation_stage=visual_assets_skipped generation_id=%s "
            "reason=no_missing_assets",
            generation_id or "unknown",
        )
        return payload, ""

    targets = [
        scene
        for scene in scenes_needing_assets
        if isinstance(scene.get("visual_prompt"), str)
        and scene["visual_prompt"].strip()
    ]
    missing_prompts = len(scenes_needing_assets) - len(targets)
    if not targets:
        logger.warning(
            "generation_stage=visual_assets_skipped generation_id=%s "
            "reason=missing_visual_prompts scenes=%s",
            generation_id or "unknown",
            missing_prompts,
        )
        return (
            payload,
            f"Assets visuais não gerados para {missing_prompts} cena(s): falta uma descrição visual.",
        )

    logger.info(
        "generation_stage=visual_assets_batch_started generation_id=%s "
        "requested_images=%s missing_prompts=%s",
        generation_id or "unknown",
        len(targets),
        missing_prompts,
    )
    attached = 0
    failures = 0
    used_seeds = set()
    for scene_index, scene in enumerate(targets, start=1):
        seed = _next_seed(used_seeds)
        prompt = _compose_image_prompt(
            scene["visual_prompt"],
            payload.get("visual_direction", ""),
            visual_theme_id,
        )
        image_started_at = monotonic()
        logger.info(
            "generation_stage=visual_asset_started generation_id=%s "
            "scene_index=%s",
            generation_id or "unknown",
            scene_index,
        )
        try:
            asset = _save_generated_image(
                prompt,
                seed,
                user,
                generation_id=generation_id,
                scene_index=scene_index,
            )
        except VisualAssetError as exc:
            failures += 1
            logger.warning(
                "generation_stage=visual_asset_failed generation_id=%s "
                "scene_index=%s error_type=%s duration_ms=%.2f",
                generation_id or "unknown",
                scene_index,
                type(exc).__name__,
                (monotonic() - image_started_at) * 1000,
            )
            continue
        except Exception:
            failures += 1
            logger.exception(
                "generation_stage=visual_asset_failed generation_id=%s "
                "scene_index=%s duration_ms=%.2f",
                generation_id or "unknown",
                scene_index,
                (monotonic() - image_started_at) * 1000,
            )
            continue

        scene.setdefault("layers", []).append(
            {
                "asset_id": str(asset.pk),
                "kind": MediaAsset.Kind.IMAGE,
                "role": "background",
                "motion": scene.get("motion", "slow_zoom"),
                "opacity": 1,
                "fit": "cover",
                "source_credit": "Imagem gerada com Pollinations.ai",
                "source_url": "https://pollinations.ai",
            }
        )
        attached += 1
        logger.info(
            "generation_stage=visual_asset_saved generation_id=%s "
            "scene_index=%s asset_id=%s size_bytes=%s duration_ms=%.2f",
            generation_id or "unknown",
            scene_index,
            asset.pk,
            asset.size_bytes,
            (monotonic() - image_started_at) * 1000,
        )

    messages = []
    if attached:
        messages.append(f"{attached} imagem(ns) gerada(s) e associada(s) automaticamente.")
    if failures:
        messages.append(
            f"Não foi possível gerar imagens para {failures} cena(s); o guião foi preservado."
        )
    if missing_prompts:
        messages.append(
            f"Assets visuais não gerados para {missing_prompts} cena(s): falta uma descrição visual."
        )
    logger.info(
        "generation_stage=visual_assets_batch_finished generation_id=%s "
        "requested_images=%s saved_images=%s failed_images=%s "
        "missing_prompts=%s",
        generation_id or "unknown",
        len(targets),
        attached,
        failures,
        missing_prompts,
    )
    return payload, " ".join(messages)
