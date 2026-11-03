import re
from pathlib import PurePosixPath

from rest_framework import serializers

from .models import MediaAsset, VideoGeneration
from .video_templates import DEFAULT_VIDEO_TEMPLATE, VIDEO_TEMPLATE_CHOICES
from .visual_themes import DEFAULT_VISUAL_THEME, VISUAL_THEME_CHOICES
from .visual_effects import (
    CAMERA_EFFECTS,
    CAMERA_EFFECT_CHOICES,
    CAMERA_INTENSITY_DEFAULT,
    CAMERA_INTENSITY_MAX,
    CAMERA_INTENSITY_MIN,
    IMAGE_TREATMENTS,
    MOTION_GRAPHICS,
    SCENE_TRANSITION_CHOICES,
    TRANSITION_DURATION_FRAMES_DEFAULT,
    TRANSITION_DURATION_FRAMES_MAX,
    TYPOGRAPHY_ANIMATIONS,
    VISUAL_DIRECTION_PLAN_VERSION,
)

COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_TOTAL_DURATION = 60
MAX_SAFE_VIDEO_FRAMES = 2**53 - 1
MAX_MEDIA_ASSET_BYTES = 100 * 1024 * 1024
ALLOWED_MEDIA_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp"},
    "video": {".mp4", ".mov", ".webm"},
    "audio": {".mp3", ".m4a", ".wav", ".ogg"},
}
MOTION_CHOICES = tuple(effect_id for effect_id, _ in CAMERA_EFFECT_CHOICES)


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown_fields = set(data) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError(
                    {
                        field: ["Este campo não é permitido."]
                        for field in sorted(unknown_fields)
                    }
                )
        return super().to_internal_value(data)


class SceneCameraPlanSerializer(StrictSerializer):
    movement = serializers.ChoiceField(choices=CAMERA_EFFECT_CHOICES)
    intensity = serializers.FloatField(
        min_value=CAMERA_INTENSITY_MIN,
        max_value=CAMERA_INTENSITY_MAX,
        default=CAMERA_INTENSITY_DEFAULT,
    )


class SceneTransitionPlanSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=SCENE_TRANSITION_CHOICES)
    duration_frames = serializers.IntegerField(
        min_value=1,
        max_value=TRANSITION_DURATION_FRAMES_MAX,
        default=TRANSITION_DURATION_FRAMES_DEFAULT,
    )


class SceneVisualPlanSerializer(StrictSerializer):
    scene_index = serializers.IntegerField(min_value=0)
    camera = SceneCameraPlanSerializer(required=False)
    transition = SceneTransitionPlanSerializer(required=False)

    def validate(self, attrs):
        if "camera" not in attrs and "transition" not in attrs:
            raise serializers.ValidationError(
                "Cada plano de cena deve definir uma câmara ou transição."
            )
        return attrs


class VisualDirectionPlanSerializer(StrictSerializer):
    schema_version = serializers.IntegerField(
        min_value=VISUAL_DIRECTION_PLAN_VERSION,
        max_value=VISUAL_DIRECTION_PLAN_VERSION,
    )
    theme = serializers.ChoiceField(choices=VISUAL_THEME_CHOICES)
    scenes = SceneVisualPlanSerializer(many=True, allow_empty=False)

    def validate_scenes(self, scenes):
        indexes = [scene["scene_index"] for scene in scenes]
        if len(indexes) != len(set(indexes)):
            raise serializers.ValidationError(
                "Cada cena pode ter apenas um plano visual."
            )
        return scenes


class SceneLayerSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField()
    kind = serializers.ChoiceField(
        choices=(
            (MediaAsset.Kind.IMAGE, "Image"),
            (MediaAsset.Kind.VIDEO, "Video"),
        )
    )
    role = serializers.ChoiceField(choices=("background", "foreground"))
    motion = serializers.ChoiceField(choices=MOTION_CHOICES, default="slow_zoom")
    opacity = serializers.FloatField(min_value=0.1, max_value=1, default=1)
    fit = serializers.ChoiceField(choices=("cover", "contain"), default="cover")
    source_credit = serializers.CharField(max_length=220, required=False, allow_blank=True)
    source_url = serializers.URLField(max_length=500, required=False, allow_blank=True)


class CaptionSegmentSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=160, allow_blank=False)
    start_seconds = serializers.FloatField(min_value=0)
    end_seconds = serializers.FloatField(min_value=0.05)


class NarrationSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    asset_id = serializers.UUIDField(required=False)
    generate_local = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs.get("generate_local") and not attrs.get("text", "").strip():
            raise serializers.ValidationError(
                {"text": "É necessário fornecer o texto da narração local."}
            )
        if attrs.get("generate_local") and attrs.get("asset_id"):
            raise serializers.ValidationError(
                "Escolha entre gerar a narração localmente ou carregar um ficheiro de áudio."
            )
        return attrs


class EndCardSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    title = serializers.CharField(max_length=100)
    subtitle = serializers.CharField(max_length=180, required=False, allow_blank=True)
    cta = serializers.CharField(max_length=80)
    duration_seconds = serializers.IntegerField(min_value=1, max_value=10)


class ScenePayloadSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=140, allow_blank=False)
    duration_seconds = serializers.IntegerField(min_value=1)
    background_color = serializers.RegexField(COLOR_PATTERN)
    image_path = serializers.CharField(max_length=180, required=False, allow_blank=True)
    visual_prompt = serializers.CharField(max_length=600, required=False, allow_blank=True)
    motion = serializers.ChoiceField(choices=MOTION_CHOICES, default="slow_zoom")
    image_treatment = serializers.ChoiceField(
        choices=tuple(IMAGE_TREATMENTS.items()),
        required=False,
    )
    typography_animation = serializers.ChoiceField(
        choices=tuple(TYPOGRAPHY_ANIMATIONS.items()),
        required=False,
    )
    motion_graphic = serializers.ChoiceField(
        choices=tuple(MOTION_GRAPHICS.items()),
        required=False,
    )
    layers = SceneLayerSerializer(many=True, required=False, max_length=4)
    captions = CaptionSegmentSerializer(many=True, required=False, max_length=30)

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

    def validate(self, attrs):
        duration = attrs["duration_seconds"]
        for caption in attrs.get("captions", []):
            if caption["start_seconds"] >= caption["end_seconds"]:
                raise serializers.ValidationError(
                    {"captions": "O início da legenda deve anteceder o fim."}
                )
            if caption["end_seconds"] > duration:
                raise serializers.ValidationError(
                    {"captions": "A legenda deve caber na duração da cena."}
                )
        layers = attrs.get("layers", [])
        if layers and sum(layer["kind"] == MediaAsset.Kind.VIDEO for layer in layers) > 1:
            raise serializers.ValidationError(
                {"layers": "Cada cena pode conter no máximo um clip de vídeo."}
            )
        return attrs

class VideoPayloadSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    template_id = serializers.ChoiceField(
        choices=VIDEO_TEMPLATE_CHOICES,
        default=DEFAULT_VIDEO_TEMPLATE,
    )
    title = serializers.CharField(max_length=100)
    visual_direction = serializers.CharField(
        max_length=400,
        required=False,
        allow_blank=True,
    )
    scenes = ScenePayloadSerializer(many=True, allow_empty=False)
    narration = NarrationSerializer(required=False)
    visual_direction_plan = VisualDirectionPlanSerializer(required=False)
    end_card = EndCardSerializer(required=False)

    def validate_schema_version(self, value):
        if value not in {1, 2}:
            raise serializers.ValidationError("Versão de payload não suportada.")
        return value

    def validate(self, attrs):
        end_card = attrs.get("end_card")
        end_card_duration = (
            end_card["duration_seconds"]
            if end_card and end_card["enabled"]
            else 0
        )
        total_duration = sum(
            scene["duration_seconds"] for scene in attrs["scenes"]
        ) + end_card_duration
        if total_duration > MAX_TOTAL_DURATION:
            raise serializers.ValidationError(
                {
                    "scenes": (
                        f"A duração total, incluindo o ecrã final, não pode "
                        f"exceder {MAX_TOTAL_DURATION} segundos."
                    )
                }
            )
        if total_duration * 30 > MAX_SAFE_VIDEO_FRAMES:
            raise serializers.ValidationError(
                "A duração excede o limite técnico de frames suportado pelo renderizador."
            )
        plan = attrs.get("visual_direction_plan")
        if plan:
            scene_indexes = {
                scene["scene_index"] for scene in plan["scenes"]
            }
            if any(index >= len(attrs["scenes"]) for index in scene_indexes):
                raise serializers.ValidationError(
                    {
                        "visual_direction_plan": {
                            "scenes": "O plano referencia uma cena inexistente."
                        }
                    }
                )
            for scene_plan in plan["scenes"]:
                if "camera" not in scene_plan:
                    continue
                scene = attrs["scenes"][scene_plan["scene_index"]]
                media_kinds = {
                    layer["kind"] for layer in scene.get("layers", [])
                }
                if scene.get("image_path"):
                    media_kinds.add(MediaAsset.Kind.IMAGE)
                effect = CAMERA_EFFECTS[scene_plan["camera"]["movement"]]
                if not media_kinds.issubset(effect["media"]):
                    raise serializers.ValidationError(
                        {
                            "visual_direction_plan": {
                                "scenes": (
                                    "O movimento seleccionado não é compatível "
                                    "com o media da cena."
                                )
                            }
                        }
                    )
        if attrs.get("narration", {}).get("generate_local"):
            if attrs["schema_version"] < 2:
                raise serializers.ValidationError(
                    {"schema_version": "A narração requer schema_version 2."}
                )
        if attrs["schema_version"] < 2 and (
            attrs.get("narration")
            or attrs.get("end_card")
            or any(
                scene.get("layers")
                or scene.get("captions")
                or any(
                    key in scene
                    for key in (
                        "image_treatment",
                        "typography_animation",
                        "motion_graphic",
                    )
                )
                for scene in attrs["scenes"]
            )
        ):
            raise serializers.ValidationError(
                {
                    "schema_version": (
                        "Os efeitos visuais, ecrã final, camadas, legendas e "
                        "narração requerem schema_version 2."
                    )
                }
            )
        return attrs

    def validate_scenes(self, scenes):
        total_duration = sum(scene["duration_seconds"] for scene in scenes)
        if total_duration > MAX_TOTAL_DURATION:
            raise serializers.ValidationError(
                f"A duração total não pode exceder {MAX_TOTAL_DURATION} segundos."
            )
        return scenes


class VideoGenerationCreateSerializer(serializers.Serializer):
    prompt = serializers.CharField(max_length=2000)
    template_id = serializers.ChoiceField(
        choices=VIDEO_TEMPLATE_CHOICES,
        default=DEFAULT_VIDEO_TEMPLATE,
    )
    visual_theme_id = serializers.ChoiceField(
        choices=VISUAL_THEME_CHOICES,
        default=DEFAULT_VISUAL_THEME,
    )
    payload = VideoPayloadSerializer(required=False)

    def validate_prompt(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("O briefing não pode estar vazio.")
        return value


class VideoGenerationRenderSerializer(serializers.Serializer):
    payload = VideoPayloadSerializer()
    visual_theme_id = serializers.ChoiceField(
        choices=VISUAL_THEME_CHOICES,
        required=False,
    )


class VideoGenerationSerializer(serializers.ModelSerializer):
    output_url = serializers.SerializerMethodField()

    class Meta:
        model = VideoGeneration
        fields = (
            "id",
            "prompt",
            "template_id",
            "visual_theme_id",
            "payload",
            "asset_pipeline_message",
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


class MediaAssetSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = (
            "id",
            "kind",
            "file",
            "file_url",
            "original_name",
            "size_bytes",
            "source_provider",
            "source_url",
            "photographer",
            "attribution_url",
            "generation_prompt",
            "generation_seed",
            "created_at",
        )
        read_only_fields = (
            "id",
            "original_name",
            "size_bytes",
            "source_provider",
            "source_url",
            "photographer",
            "attribution_url",
            "generation_prompt",
            "generation_seed",
            "created_at",
        )

    def get_file_url(self, obj):
        request = self.context.get("request")
        url = f"/api/v1/videos/assets/{obj.pk}/file/"
        return request.build_absolute_uri(url) if request else url

    def validate_file(self, value):
        if value.size > MAX_MEDIA_ASSET_BYTES:
            raise serializers.ValidationError("O ficheiro não pode exceder 100 MB.")
        return value

    def validate(self, attrs):
        uploaded_file = attrs["file"]
        extension = PurePosixPath(uploaded_file.name).suffix.lower()
        kind = attrs["kind"]
        if extension not in ALLOWED_MEDIA_EXTENSIONS[kind]:
            raise serializers.ValidationError(
                {"file": "A extensão do ficheiro não corresponde ao tipo de media."}
            )
        return attrs

    def create(self, validated_data):
        uploaded_file = validated_data.pop("file")
        request = self.context["request"]
        return MediaAsset.objects.create(
            user=request.user,
            kind=validated_data["kind"],
            file=uploaded_file,
            original_name=uploaded_file.name[:255],
            size_bytes=uploaded_file.size,
        )
