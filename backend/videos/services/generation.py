import copy
import logging
import tempfile
from time import monotonic
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.utils import timezone

from videos.models import VideoGeneration
from videos.services.agent import AgentGenerationError, generate_video_payload
from videos.services.media_assets import MediaAssetError, stage_render_assets
from videos.services.narration import LocalNarrationError, generate_local_narration
from videos.services.remotion import RemotionRenderError, render_video
from videos.services.visual_assets import prepare_visual_assets

logger = logging.getLogger(__name__)


def generate_video_script(generation_id, *, raise_errors=True):
    started_at = monotonic()
    logger.info(
        "generation_stage=script_task_started generation_id=%s",
        generation_id,
    )
    generation = VideoGeneration.objects.get(pk=generation_id)
    if generation.status in {
        VideoGeneration.Status.DRAFT,
        VideoGeneration.Status.RENDER_QUEUED,
        VideoGeneration.Status.RENDERING,
        VideoGeneration.Status.COMPLETED,
    }:
        logger.info(
            "generation_stage=script_task_skipped generation_id=%s status=%s",
            generation.pk,
            generation.status,
        )
        return str(generation.pk)

    generation.status = VideoGeneration.Status.WRITING_SCRIPT
    generation.error_message = ""
    generation.save(update_fields=("status", "error_message"))
    logger.info(
        "generation_stage=status_changed generation_id=%s status=%s",
        generation.pk,
        generation.status,
    )

    try:
        if not generation.payload:
            logger.info(
                "generation_stage=agent_started generation_id=%s",
                generation.pk,
            )
            agent_started_at = monotonic()
            generation.payload = generate_video_payload(
                generation.prompt,
                template_id=generation.template_id,
                visual_theme_id=generation.visual_theme_id,
                generation_id=str(generation.pk),
            )
            logger.info(
                "generation_stage=agent_succeeded generation_id=%s scenes=%s "
                "duration_ms=%.2f",
                generation.pk,
                len(generation.payload.get("scenes", [])),
                (monotonic() - agent_started_at) * 1000,
            )
            logger.info(
                "generation_stage=visual_assets_started generation_id=%s",
                generation.pk,
            )
            assets_started_at = monotonic()
            generation.payload, generation.asset_pipeline_message = (
                prepare_visual_assets(
                    generation.payload,
                    generation.user,
                    visual_theme_id=generation.visual_theme_id,
                    generation_id=str(generation.pk),
                )
            )
            logger.info(
                "generation_stage=visual_assets_finished generation_id=%s "
                "duration_ms=%.2f",
                generation.pk,
                (monotonic() - assets_started_at) * 1000,
            )
        else:
            logger.info(
                "generation_stage=agent_and_assets_skipped generation_id=%s "
                "reason=payload_already_present",
                generation.pk,
            )
        generation.payload["template_id"] = generation.template_id
        generation.status = VideoGeneration.Status.DRAFT
        save_started_at = monotonic()
        generation.save(
            update_fields=("payload", "asset_pipeline_message", "status")
        )
        logger.info(
            "generation_stage=script_persisted generation_id=%s status=%s "
            "scenes=%s assets_message_present=%s duration_ms=%.2f",
            generation.pk,
            generation.status,
            len(generation.payload.get("scenes", [])),
            bool(generation.asset_pipeline_message),
            (monotonic() - save_started_at) * 1000,
        )
    except AgentGenerationError as exc:
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = str(exc)
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.warning(
            "generation_stage=script_failed generation_id=%s "
            "error_type=%s duration_ms=%.2f",
            generation.pk,
            type(exc).__name__,
            (monotonic() - started_at) * 1000,
        )
        if raise_errors:
            raise
    except Exception:
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = "Ocorreu um erro interno ao criar o guião."
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.exception(
            "generation_stage=script_failed generation_id=%s "
            "duration_ms=%.2f",
            generation.pk,
            (monotonic() - started_at) * 1000,
        )
        if raise_errors:
            raise

    logger.info(
        "generation_stage=script_task_finished generation_id=%s status=%s "
        "duration_ms=%.2f",
        generation.pk,
        generation.status,
        (monotonic() - started_at) * 1000,
    )
    return str(generation.pk)


def render_video_generation(generation_id, *, raise_errors=True):
    started_at = monotonic()
    logger.info(
        "generation_stage=render_task_started generation_id=%s",
        generation_id,
    )
    generation = VideoGeneration.objects.get(pk=generation_id)
    if generation.status == VideoGeneration.Status.COMPLETED:
        logger.info(
            "generation_stage=render_task_skipped generation_id=%s "
            "reason=already_completed",
            generation.pk,
        )
        return str(generation.pk)
    if not generation.payload:
        raise ValueError("A generation needs an approved script before rendering.")

    generation.status = VideoGeneration.Status.RENDERING
    generation.started_at = timezone.now()
    generation.error_message = ""
    generation.save(update_fields=("status", "started_at", "error_message"))
    logger.info(
        "generation_stage=status_changed generation_id=%s status=%s",
        generation.pk,
        generation.status,
    )

    try:
        with tempfile.TemporaryDirectory(prefix=f"video-{generation.pk}-") as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / f"{generation.pk}.mp4"
            render_payload = copy.deepcopy(generation.payload)
            render_payload["visual_theme_id"] = generation.visual_theme_id
            narration = render_payload.get("narration", {})
            generated_audio_path = None
            if narration.get("generate_local"):
                narration_started_at = monotonic()
                logger.info(
                    "generation_stage=narration_started generation_id=%s",
                    generation.pk,
                )
                generated_audio_path = generate_local_narration(
                    narration["text"],
                    temp_path / "narration.wav",
                )
                logger.info(
                    "generation_stage=narration_finished generation_id=%s "
                    "duration_ms=%.2f",
                    generation.pk,
                    (monotonic() - narration_started_at) * 1000,
                )
            previous_output_name = generation.output_file.name
            staging_started_at = monotonic()
            logger.info(
                "generation_stage=render_assets_staging_started "
                "generation_id=%s",
                generation.pk,
            )
            with stage_render_assets(
                render_payload,
                generation.user,
                settings.REMOTION_PROJECT_DIR,
                generated_audio_path=generated_audio_path,
            ) as staged_payload:
                logger.info(
                    "generation_stage=render_assets_staged generation_id=%s "
                    "duration_ms=%.2f",
                    generation.pk,
                    (monotonic() - staging_started_at) * 1000,
                )
                remotion_started_at = monotonic()
                logger.info(
                    "generation_stage=remotion_started generation_id=%s",
                    generation.pk,
                )
                render_video(staged_payload, output_path)
                logger.info(
                    "generation_stage=remotion_finished generation_id=%s "
                    "output_bytes=%s duration_ms=%.2f",
                    generation.pk,
                    output_path.stat().st_size,
                    (monotonic() - remotion_started_at) * 1000,
                )
                with output_path.open("rb") as output:
                    generation.output_file.save(
                        f"{generation.pk}.mp4", File(output), save=False
                    )
            logger.info(
                "generation_stage=output_stored generation_id=%s file_name=%s",
                generation.pk,
                generation.output_file.name,
            )

        generation.status = VideoGeneration.Status.COMPLETED
        generation.completed_at = timezone.now()
        generation.save(
            update_fields=("output_file", "status", "completed_at", "error_message")
        )
        if (
            previous_output_name
            and previous_output_name != generation.output_file.name
        ):
            generation.output_file.storage.delete(previous_output_name)
        logger.info(
            "generation_stage=render_task_finished generation_id=%s status=%s "
            "duration_ms=%.2f",
            generation.pk,
            generation.status,
            (monotonic() - started_at) * 1000,
        )
    except (RemotionRenderError, LocalNarrationError, MediaAssetError, OSError) as exc:
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = (
            str(exc)
            if isinstance(exc, (LocalNarrationError, MediaAssetError))
            else "A renderização falhou. Tente novamente mais tarde."
        )
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.exception(
            "generation_stage=render_failed generation_id=%s error_type=%s "
            "duration_ms=%.2f",
            generation.pk,
            type(exc).__name__,
            (monotonic() - started_at) * 1000,
        )
        if raise_errors:
            raise
    except Exception:
        generation.status = VideoGeneration.Status.FAILED
        generation.error_message = "Ocorreu um erro interno durante a renderização."
        generation.completed_at = timezone.now()
        generation.save(update_fields=("status", "error_message", "completed_at"))
        logger.exception(
            "generation_stage=render_failed generation_id=%s "
            "duration_ms=%.2f",
            generation.pk,
            (monotonic() - started_at) * 1000,
        )
        if raise_errors:
            raise

    return str(generation.pk)
