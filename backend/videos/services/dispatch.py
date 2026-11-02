from django.conf import settings

from .generation import generate_video_script, render_video_generation


class TaskQueueUnavailable(RuntimeError):
    pass


def enqueue_task(task_name, generation_id):
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


def dispatch_script_generation(generation_id):
    if settings.VIDEO_RENDER_MODE == "inline":
        generate_video_script(generation_id, raise_errors=False)
        return

    enqueue_task("generate_video_script_task", generation_id)


def dispatch_video_render(generation_id):
    if settings.VIDEO_RENDER_MODE == "inline":
        render_video_generation(generation_id, raise_errors=False)
        return

    enqueue_task("render_video_task", generation_id)
