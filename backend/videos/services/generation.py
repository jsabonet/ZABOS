import logging
import tempfile
from pathlib import Path

from django.core.files import File
from django.utils import timezone

from videos.models import VideoGeneration
from videos.services.agent import AgentGenerationError, generate_video_payload
from videos.services.remotion import RemotionRenderError, render_video

logger = logging.getLogger(__name__)


def generate_video_script(generation_id, *, raise_errors=True):
    generation = VideoGeneration.objects.get(pk=generation_id)
    if generation.status in {
        VideoGeneration.Status.DRAFT,
        VideoGeneration.Status.RENDER_QUEUED,
        VideoGeneration.Status.RENDERING,
        VideoGeneration.Status.COMPLETED,
    }:
        return str(generation.pk)

    generation.status = VideoGeneration.Status.WRITING_SCRIPT
    generation.error_message = ""
    generation.save(update_fields=("status", "error_message"))

    try:
        if not generation.payload:
            generation.payload = generate_video_payload(generation.prompt)
        generation.status = VideoGeneration.Status.DRAFT
        generation.save(update_fields=("payload", "status"))
    except AgentGenerationError as exc:
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = str(exc)
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.warning("Agent generation failed for %s: %s", generation.pk, exc)
        if raise_errors:
            raise
    except Exception:
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = "Ocorreu um erro interno ao criar o guião."
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.exception("Unexpected script generation failure for %s", generation.pk)
        if raise_errors:
            raise

    return str(generation.pk)


def render_video_generation(generation_id, *, raise_errors=True):
    generation = VideoGeneration.objects.get(pk=generation_id)
    if generation.status == VideoGeneration.Status.COMPLETED:
        return str(generation.pk)
    if not generation.payload:
        raise ValueError("A generation needs an approved script before rendering.")

    generation.status = VideoGeneration.Status.RENDERING
    generation.started_at = timezone.now()
    generation.error_message = ""
    generation.save(update_fields=("status", "started_at", "error_message"))

    try:
        with tempfile.TemporaryDirectory(prefix=f"video-{generation.pk}-") as temp_dir:
            output_path = Path(temp_dir) / f"{generation.pk}.mp4"
            render_video(generation.payload, output_path)
            with output_path.open("rb") as output:
                generation.output_file.save(
                    f"{generation.pk}.mp4", File(output), save=False
                )

        generation.status = VideoGeneration.Status.COMPLETED
        generation.completed_at = timezone.now()
        generation.save(
            update_fields=("output_file", "status", "completed_at", "error_message")
        )
    except (RemotionRenderError, OSError):
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = "A renderização falhou. Tente novamente mais tarde."
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.exception("Render failed for generation %s", generation.pk)
        if raise_errors:
            raise
    except Exception:
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = "Ocorreu um erro interno durante a renderização."
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.exception("Unexpected render failure for generation %s", generation.pk)
        if raise_errors:
            raise

    return str(generation.pk)
