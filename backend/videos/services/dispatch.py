import logging
from time import monotonic

from django.conf import settings

from .generation import generate_video_script, render_video_generation

logger = logging.getLogger(__name__)


class TaskQueueUnavailable(RuntimeError):
    pass


def enqueue_task(task_name, generation_id):
    started_at = monotonic()
    logger.info(
        "generation_stage=queue_publish_started generation_id=%s task=%s",
        generation_id,
        task_name,
    )
    try:
        from kombu.exceptions import OperationalError
        from videos import tasks
    except ImportError as exc:
        raise TaskQueueUnavailable(
            "O modo com fila requer as dependências em requirements-async.txt."
        ) from exc

    try:
        getattr(tasks, task_name).delay(str(generation_id))
    except OperationalError as exc:
        raise TaskQueueUnavailable(
            "A fila de tarefas está indisponível. Confirme se o Redis está activo."
        ) from exc
    logger.info(
        "generation_stage=queue_publish_succeeded generation_id=%s task=%s "
        "duration_ms=%.2f",
        generation_id,
        task_name,
        (monotonic() - started_at) * 1000,
    )


def dispatch_script_generation(generation_id):
    if settings.VIDEO_RENDER_MODE == "inline":
        logger.info(
            "generation_stage=dispatch_inline generation_id=%s operation=script",
            generation_id,
        )
        generate_video_script(generation_id, raise_errors=False)
        return

    logger.info(
        "generation_stage=dispatch_queued generation_id=%s operation=script",
        generation_id,
    )
    enqueue_task("generate_video_script_task", generation_id)


def dispatch_video_render(generation_id):
    if settings.VIDEO_RENDER_MODE == "inline":
        logger.info(
            "generation_stage=dispatch_inline generation_id=%s operation=render",
            generation_id,
        )
        render_video_generation(generation_id, raise_errors=False)
        return

    logger.info(
        "generation_stage=dispatch_queued generation_id=%s operation=render",
        generation_id,
    )
    enqueue_task("render_video_task", generation_id)
