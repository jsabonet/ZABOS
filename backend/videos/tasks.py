from celery import shared_task

from .services.generation import generate_video_script, render_video_generation


@shared_task
def generate_video_script_task(generation_id):
    return generate_video_script(generation_id)


@shared_task
def render_video_task(generation_id):
    return render_video_generation(generation_id)
