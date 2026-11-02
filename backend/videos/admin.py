from django.contrib import admin

from .models import VideoGeneration


@admin.register(VideoGeneration)
class VideoGenerationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "created_at", "completed_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "user__username", "prompt")
    readonly_fields = ("id", "created_at", "started_at", "completed_at")
