import logging

from django.conf import settings
from django.http import FileResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VideoGeneration
from .serializers import (
    VideoGenerationCreateSerializer,
    VideoGenerationSerializer,
    VideoPayloadSerializer,
)
from .services.dispatch import (
    TaskQueueUnavailable,
    dispatch_script_generation,
    dispatch_video_render,
)

logger = logging.getLogger(__name__)

class TaskQueueUnavailableAPIException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "task_queue_unavailable"


class VideoGenerationListCreateView(generics.ListCreateAPIView):
    serializer_class = VideoGenerationSerializer

    def get_queryset(self):
        return VideoGeneration.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        input_serializer = VideoGenerationCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        generation = None
        try:
            with transaction.atomic():
                generation = VideoGeneration.objects.create(
                    user=request.user,
                    prompt=input_serializer.validated_data["prompt"],
                    payload=input_serializer.validated_data.get("payload", {}),
                )
                transaction.on_commit(
                    lambda: dispatch_script_generation(generation.pk)
                )
        except TaskQueueUnavailable as exc:
            logger.error("Task broker is unavailable while queuing a render")
            if generation is not None:
                generation.status = VideoGeneration.Status.FAILED
                generation.error_message = str(exc)
                generation.completed_at = timezone.now()
                generation.save(
                    update_fields=("status", "error_message", "completed_at")
                )
            raise TaskQueueUnavailableAPIException(
                detail=str(exc),
                code="task_queue_unavailable",
            ) from exc
        except Exception as exc:
            logger.exception("Could not enqueue video generation")
            if generation is not None:
                generation.status = VideoGeneration.Status.FAILED
                generation.error_message = "Não foi possível agendar a renderização."
                generation.completed_at = timezone.now()
                generation.save(
                    update_fields=("status", "error_message", "completed_at")
                )
            raise APIException("Não foi possível agendar a renderização.") from exc

        generation.refresh_from_db()
        output = VideoGenerationSerializer(
            generation, context=self.get_serializer_context()
        )
        response_status = (
            status.HTTP_201_CREATED
            if settings.VIDEO_RENDER_MODE == "inline"
            else status.HTTP_202_ACCEPTED
        )
        return Response(output.data, status=response_status)


class VideoGenerationRenderView(APIView):
    def post(self, request, generation_id):
        generation = get_object_or_404(
            VideoGeneration,
            pk=generation_id,
            user=request.user,
        )
        if generation.status not in {
            VideoGeneration.Status.DRAFT,
            VideoGeneration.Status.FAILED,
        }:
            raise ValidationError(
                {"detail": "Este guião não está disponível para renderização."},
                code="generation_not_ready",
            )

        payload_serializer = VideoPayloadSerializer(data=request.data.get("payload"))
        payload_serializer.is_valid(raise_exception=True)
        generation.payload = payload_serializer.validated_data

        try:
            with transaction.atomic():
                generation.save(update_fields=("payload",))
                if settings.VIDEO_RENDER_MODE == "celery":
                    generation.status = VideoGeneration.Status.RENDER_QUEUED
                    generation.save(update_fields=("status",))
                transaction.on_commit(
                    lambda: dispatch_video_render(generation.pk)
                )
        except TaskQueueUnavailable as exc:
            logger.error("Task broker is unavailable while queuing a render")
            generation.status = VideoGeneration.Status.DRAFT
            generation.error_message = str(exc)
            generation.save(update_fields=("status", "error_message"))
            raise TaskQueueUnavailableAPIException(
                detail=str(exc),
                code="task_queue_unavailable",
            ) from exc
        except Exception as exc:
            logger.exception("Could not start video render")
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
