import logging
import json
import mimetypes
from time import monotonic

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MediaAsset, VideoGeneration
from .serializers import (
    MediaAssetSerializer,
    VideoGenerationCreateSerializer,
    VideoGenerationRenderSerializer,
    VideoGenerationSerializer,
)
from .services.dispatch import (
    TaskQueueUnavailable,
    dispatch_script_generation,
    dispatch_video_render,
)
from .services.media_assets import MediaAssetError, validate_asset_ownership

logger = logging.getLogger(__name__)


class TaskQueueUnavailableAPIException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "task_queue_unavailable"


def json_safe_payload(payload):
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


class VideoGenerationListCreateView(generics.ListCreateAPIView):
    serializer_class = VideoGenerationSerializer

    def get_queryset(self):
        return VideoGeneration.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        started_at = monotonic()
        logger.info(
            "generation_stage=request_received user_id=%s method=%s",
            request.user.pk,
            request.method,
        )
        input_serializer = VideoGenerationCreateSerializer(data=request.data)
        try:
            input_serializer.is_valid(raise_exception=True)
        except ValidationError:
            logger.warning(
                "generation_stage=request_validation_failed user_id=%s",
                request.user.pk,
            )
            raise
        payload = json_safe_payload(
            input_serializer.validated_data.get("payload", {})
        )
        logger.info(
            "generation_stage=request_validated user_id=%s template_id=%s "
            "visual_theme_id=%s supplied_payload=%s",
            request.user.pk,
            input_serializer.validated_data["template_id"],
            input_serializer.validated_data["visual_theme_id"],
            bool(payload),
        )
        logger.info(
            "generation_stage=asset_ownership_validation_started user_id=%s",
            request.user.pk,
        )
        try:
            validate_asset_ownership(payload, request.user)
        except MediaAssetError as exc:
            logger.warning(
                "generation_stage=asset_ownership_validation_failed user_id=%s "
                "error_type=%s",
                request.user.pk,
                type(exc).__name__,
            )
            raise ValidationError({"payload": str(exc)}) from exc
        logger.info(
            "generation_stage=asset_ownership_validated user_id=%s",
            request.user.pk,
        )
        persistence_started_at = monotonic()
        logger.info(
            "generation_stage=persistence_started user_id=%s",
            request.user.pk,
        )
        try:
            with transaction.atomic():
                generation = VideoGeneration.objects.create(
                    user=request.user,
                    prompt=input_serializer.validated_data["prompt"],
                    template_id=input_serializer.validated_data["template_id"],
                    visual_theme_id=input_serializer.validated_data["visual_theme_id"],
                    payload=payload,
                )
        except Exception as exc:
            logger.exception(
                "generation_stage=persistence_failed user_id=%s",
                request.user.pk,
            )
            raise APIException("Não foi possível criar o projecto.") from exc
        logger.info(
            "generation_stage=persisted generation_id=%s user_id=%s "
            "duration_ms=%.2f",
            generation.pk,
            request.user.pk,
            (monotonic() - persistence_started_at) * 1000,
        )

        dispatch_error = ""
        logger.info(
            "generation_stage=dispatch_started generation_id=%s mode=%s",
            generation.pk,
            settings.VIDEO_RENDER_MODE,
        )
        try:
            dispatch_script_generation(generation.pk)
        except TaskQueueUnavailable as exc:
            dispatch_error = str(exc)
            logger.error(
                "generation_stage=dispatch_failed generation_id=%s "
                "error_type=%s",
                generation.pk,
                type(exc).__name__,
            )
        except Exception:
            dispatch_error = "Não foi possível iniciar a criação do guião."
            logger.exception(
                "generation_stage=dispatch_failed generation_id=%s",
                generation.pk,
            )

        if dispatch_error:
            generation.status = VideoGeneration.Status.FAILED
            generation.error_message = dispatch_error
            generation.completed_at = timezone.now()
            generation.save(
                update_fields=("status", "error_message", "completed_at")
            )
            logger.warning(
                "generation_stage=marked_failed generation_id=%s",
                generation.pk,
            )

        generation.refresh_from_db()
        output = VideoGenerationSerializer(
            generation, context=self.get_serializer_context()
        )
        response_status = (
            status.HTTP_202_ACCEPTED
            if settings.VIDEO_RENDER_MODE == "celery" and not dispatch_error
            else status.HTTP_201_CREATED
        )
        logger.info(
            "generation_stage=response_ready generation_id=%s status=%s "
            "http_status=%s total_duration_ms=%.2f",
            generation.pk,
            generation.status,
            response_status,
            (monotonic() - started_at) * 1000,
        )
        return Response(output.data, status=response_status)


class VideoGenerationRenderView(APIView):
    def post(self, request, generation_id):
        started_at = monotonic()
        logger.info(
            "generation_stage=render_request_received generation_id=%s "
            "user_id=%s method=%s",
            generation_id,
            request.user.pk,
            request.method,
        )
        generation = get_object_or_404(
            VideoGeneration,
            pk=generation_id,
            user=request.user,
        )
        input_serializer = VideoGenerationRenderSerializer(data=request.data)
        try:
            input_serializer.is_valid(raise_exception=True)
        except ValidationError:
            logger.warning(
                "generation_stage=render_request_validation_failed "
                "generation_id=%s user_id=%s",
                generation.pk,
                request.user.pk,
            )
            raise
        payload = json_safe_payload(input_serializer.validated_data["payload"])
        logger.info(
            "generation_stage=render_request_validated generation_id=%s "
            "scenes=%s",
            generation.pk,
            len(payload.get("scenes", [])),
        )
        try:
            validate_asset_ownership(payload, request.user)
        except MediaAssetError as exc:
            logger.warning(
                "generation_stage=render_asset_validation_failed "
                "generation_id=%s error_type=%s",
                generation.pk,
                type(exc).__name__,
            )
            raise ValidationError({"payload": str(exc)}) from exc
        visual_theme_id = input_serializer.validated_data.get(
            "visual_theme_id", generation.visual_theme_id
        )
        if generation.status == VideoGeneration.Status.COMPLETED:
            if visual_theme_id == generation.visual_theme_id:
                raise ValidationError(
                    {"detail": "Escolha outro tema visual para criar uma nova versão."},
                    code="theme_unchanged",
                )
        elif generation.status not in {
            VideoGeneration.Status.DRAFT,
            VideoGeneration.Status.FAILED,
        }:
            raise ValidationError(
                {"detail": "Este guião não está disponível para renderização."},
                code="generation_not_ready",
            )

        previous_status = generation.status
        previous_payload = generation.payload
        previous_theme_id = generation.visual_theme_id
        generation.payload = payload
        generation.payload["template_id"] = generation.template_id
        generation.visual_theme_id = visual_theme_id
        logger.info(
            "generation_stage=render_dispatch_started generation_id=%s "
            "mode=%s",
            generation.pk,
            settings.VIDEO_RENDER_MODE,
        )

        try:
            with transaction.atomic():
                generation.save(update_fields=("payload", "visual_theme_id"))
                if settings.VIDEO_RENDER_MODE == "celery":
                    generation.status = VideoGeneration.Status.RENDER_QUEUED
                    generation.save(update_fields=("status",))
                else:
                    generation.status = VideoGeneration.Status.RENDERING
                    generation.save(update_fields=("status",))
                transaction.on_commit(
                    lambda: dispatch_video_render(generation.pk)
                )
        except TaskQueueUnavailable as exc:
            logger.error(
                "generation_stage=render_dispatch_failed generation_id=%s "
                "error_type=%s",
                generation.pk,
                type(exc).__name__,
            )
            generation.status = previous_status
            generation.payload = previous_payload
            generation.visual_theme_id = previous_theme_id
            generation.error_message = str(exc)
            generation.save(
                update_fields=("status", "payload", "visual_theme_id", "error_message")
            )
            raise TaskQueueUnavailableAPIException(
                detail=str(exc),
                code="task_queue_unavailable",
            ) from exc
        except Exception as exc:
            logger.exception(
                "generation_stage=render_dispatch_failed generation_id=%s",
                generation.pk,
            )
            generation.status = previous_status
            generation.payload = previous_payload
            generation.visual_theme_id = previous_theme_id
            generation.save(
                update_fields=("status", "payload", "visual_theme_id")
            )
            raise APIException("Não foi possível iniciar a renderização.") from exc

        generation.refresh_from_db()
        output = VideoGenerationSerializer(
            generation, context={"request": request}
        )
        response_status = (
            status.HTTP_200_OK
            if settings.VIDEO_RENDER_MODE == "inline"
            else status.HTTP_202_ACCEPTED
        )
        logger.info(
            "generation_stage=render_response_ready generation_id=%s "
            "status=%s http_status=%s total_duration_ms=%.2f",
            generation.pk,
            generation.status,
            response_status,
            (monotonic() - started_at) * 1000,
        )
        return Response(output.data, status=response_status)


class VideoGenerationDetailView(generics.RetrieveAPIView):
    serializer_class = VideoGenerationSerializer
    queryset = VideoGeneration.objects.all()
    lookup_field = "id"
    lookup_url_kwarg = "generation_id"

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class VideoGenerationFileView(APIView):
    def get(self, request, generation_id):
        generation = get_object_or_404(
            VideoGeneration,
            pk=generation_id,
            user=request.user,
            status=VideoGeneration.Status.COMPLETED,
        )
        if not generation.output_file:
            raise APIException("O ficheiro da geração concluída não está disponível.")
        return FileResponse(
            generation.output_file.open("rb"),
            content_type="video/mp4",
            as_attachment=False,
            filename=f"{generation.pk}.mp4",
        )


class MediaAssetListCreateView(generics.ListCreateAPIView):
    serializer_class = MediaAssetSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        return MediaAsset.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        uploaded_file = serializer.validated_data["file"]
        started_at = monotonic()
        logger.info(
            "media_asset_stage=upload_started user_id=%s kind=%s size_bytes=%s",
            self.request.user.pk,
            serializer.validated_data["kind"],
            uploaded_file.size,
        )
        try:
            asset = serializer.save(user=self.request.user)
        except Exception:
            logger.exception(
                "media_asset_stage=upload_failed user_id=%s kind=%s",
                self.request.user.pk,
                serializer.validated_data["kind"],
            )
            raise
        logger.info(
            "media_asset_stage=upload_succeeded asset_id=%s user_id=%s "
            "kind=%s size_bytes=%s duration_ms=%.2f",
            asset.pk,
            self.request.user.pk,
            asset.kind,
            asset.size_bytes,
            (monotonic() - started_at) * 1000,
        )


class MediaAssetFileView(APIView):
    def get(self, request, asset_id):
        asset = get_object_or_404(MediaAsset, pk=asset_id, user=request.user)
        return FileResponse(
            asset.file.open("rb"),
            content_type=mimetypes.guess_type(asset.original_name)[0]
            or "application/octet-stream",
            as_attachment=False,
            filename=asset.original_name,
        )
