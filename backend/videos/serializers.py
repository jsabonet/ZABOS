import re
from pathlib import PurePosixPath

from rest_framework import serializers

from .models import VideoGeneration

COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SCENES = 8
MAX_TOTAL_DURATION = 60


class ScenePayloadSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=140, allow_blank=False)
    duration_seconds = serializers.IntegerField(min_value=1, max_value=10)
    background_color = serializers.RegexField(COLOR_PATTERN)
    image_path = serializers.CharField(max_length=180, required=False, allow_blank=True)

    def validate_image_path(self, value):
        if not value:
            return ""
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or "\\" in value
            or any(part in ("", ".", "..") for part in path.parts)
            or not value.startswith("assets/")
        ):
            raise serializers.ValidationError("Use apenas caminhos relativos dentro de assets/.")
        return value


class VideoPayloadSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    title = serializers.CharField(max_length=100)
    scenes = ScenePayloadSerializer(many=True, allow_empty=False)

    def validate_schema_version(self, value):
        if value != 1:
            raise serializers.ValidationError("Versão de payload não suportada.")
        return value

    def validate_scenes(self, scenes):
        if len(scenes) > MAX_SCENES:
            raise serializers.ValidationError(f"O máximo permitido é {MAX_SCENES} cenas.")
        if sum(scene["duration_seconds"] for scene in scenes) > MAX_TOTAL_DURATION:
            raise serializers.ValidationError(
                f"A duração total não pode exceder {MAX_TOTAL_DURATION} segundos."
            )
        return scenes


class VideoGenerationCreateSerializer(serializers.Serializer):
    prompt = serializers.CharField(max_length=2000)
    payload = VideoPayloadSerializer(required=False)

    def validate_prompt(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("O briefing não pode estar vazio.")
        return value


class VideoGenerationSerializer(serializers.ModelSerializer):
    output_url = serializers.SerializerMethodField()

    class Meta:
        model = VideoGeneration
        fields = (
            "id",
            "prompt",
            "payload",
            "status",
            "error_message",
            "created_at",
            "started_at",
            "completed_at",
            "output_url",
        )
        read_only_fields = fields

    def get_output_url(self, obj):
        if not obj.output_file:
            return None
        request = self.context.get("request")
        url = f"/api/v1/videos/{obj.pk}/file/"
        return request.build_absolute_uri(url) if request else url
