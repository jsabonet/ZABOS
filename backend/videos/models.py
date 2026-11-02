import uuid

from django.conf import settings
from django.db import models


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
    payload = models.JSONField()
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
