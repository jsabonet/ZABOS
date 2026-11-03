import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from .video_templates import DEFAULT_VIDEO_TEMPLATE, VIDEO_TEMPLATE_CHOICES
from .visual_themes import DEFAULT_VISUAL_THEME, VISUAL_THEME_CHOICES


def media_asset_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"assets/{instance.user_id}/{uuid.uuid4().hex}{extension}"


class MediaAsset(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="video_assets",
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    file = models.FileField(upload_to=media_asset_upload_path)
    original_name = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    source_provider = models.CharField(max_length=32, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    photographer = models.CharField(max_length=160, blank=True)
    attribution_url = models.URLField(max_length=500, blank=True)
    generation_prompt = models.TextField(blank=True)
    generation_seed = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("user", "kind", "-created_at"))]

    def __str__(self):
        return f"{self.original_name} ({self.kind})"


class VideoGeneration(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        WRITING_SCRIPT = "writing_script", "Writing script"
        DRAFT = "draft", "Draft review"
        PROCESSING = "processing", "Processing"
        RENDER_QUEUED = "render_queued", "Render queued"
        RENDERING = "rendering", "Rendering"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="video_generations",
    )
    prompt = models.CharField(max_length=2000)
    template_id = models.CharField(
        max_length=32,
        choices=VIDEO_TEMPLATE_CHOICES,
        default=DEFAULT_VIDEO_TEMPLATE,
    )
    visual_theme_id = models.CharField(
        max_length=32,
        choices=VISUAL_THEME_CHOICES,
        default=DEFAULT_VISUAL_THEME,
    )
    payload = models.JSONField()
    asset_pipeline_message = models.CharField(max_length=300, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    output_file = models.FileField(upload_to="videos/%Y/%m/", blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "-created_at")),
            models.Index(fields=("status", "created_at")),
        ]

    def __str__(self):
        return f"{self.id} ({self.status})"
