import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import VideoGeneration
from .serializers import VideoPayloadSerializer
from .services.agent import AgentGenerationError, generate_video_payload
from .services.dispatch import TaskQueueUnavailable
from .services.generation import generate_video_script, render_video_generation
from .services.remotion import RemotionRenderError


def valid_payload():
    return {
        "schema_version": 1,
        "title": "Dica rápida",
        "scenes": [
            {
                "text": "Uma dica para o seu negócio",
                "duration_seconds": 4,
                "background_color": "#102030",
            }
        ],
    }


class VideoPayloadSerializerTests(TestCase):
    def test_accepts_valid_payload(self):
        serializer = VideoPayloadSerializer(data=valid_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_path_traversal_in_image_path(self):
        payload = valid_payload()
        payload["scenes"][0]["image_path"] = "assets/../../private.jpg"
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_rejects_duration_over_limit(self):
        payload = valid_payload()
        payload["scenes"] = [
            {
                "text": "Frame",
                "duration_seconds": 10,
                "background_color": "#102030",
            }
        ] * 7
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())


class VideoGenerationApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="creator",
            password="secure-test-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="another",
            password="secure-test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @override_settings(VIDEO_RENDER_MODE="celery")
    @patch("videos.services.dispatch.enqueue_task")
    def test_create_returns_accepted_and_queues_script_job(self, enqueue):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/videos/",
                {"prompt": "Criar uma dica"},
                format="json",
            )

        self.assertEqual(response.status_code, 202)
        generation = VideoGeneration.objects.get()
        self.assertEqual(generation.user, self.user)
        self.assertEqual(generation.status, VideoGeneration.Status.QUEUED)
        self.assertEqual(generation.payload, {})
        enqueue.assert_called_once_with("generate_video_script_task", generation.pk)

    def test_user_cannot_retrieve_another_users_generation(self):
        generation = VideoGeneration.objects.create(
            user=self.other_user,
            prompt="Outro utilizador",
            payload=valid_payload(),
        )
        response = self.client.get(f"/api/v1/videos/{generation.pk}/")

        self.assertEqual(response.status_code, 404)

    def test_completed_video_is_served_inline_to_owner(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                generation = VideoGeneration.objects.create(
                    user=self.user,
                    prompt="Criar uma dica",
                    payload=valid_payload(),
                    status=VideoGeneration.Status.COMPLETED,
                )
                generation.output_file.save(
                    "test.mp4", ContentFile(b"fake-mp4"), save=True
                )

                response = self.client.get(f"/api/v1/videos/{generation.pk}/file/")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "video/mp4")
                self.assertNotIn("attachment", response.get("Content-Disposition", ""))
                response.close()
                generation.output_file.delete(save=False)

    def test_creation_requires_authentication(self):
        self.client.force_authenticate(None)
        response = self.client.post(
            "/api/v1/videos/",
            {"prompt": "Criar uma dica", "payload": valid_payload()},
            format="json",
        )

        self.assertEqual(response.status_code, 401)


class VideoInlineApiTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inline-creator",
            password="secure-test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @override_settings(VIDEO_RENDER_MODE="inline")
    @patch(
        "videos.services.generation.generate_video_payload",
        return_value={
            "schema_version": 1,
            "title": "Dica rápida",
            "scenes": [
                {
                    "text": "Uma dica para o seu negócio",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                }
            ],
        },
    )
    @patch("videos.services.generation.render_video")
    def test_local_mode_creates_reviewable_script_before_render(
        self, render, generate
    ):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                def write_mp4(payload, destination):
                    Path(destination).write_bytes(b"fake-mp4")
                    return Path(destination)

                render.side_effect = write_mp4
                response = self.client.post(
                    "/api/v1/videos/",
                    {"prompt": "Criar uma dica"},
                    format="json",
                )

                self.assertEqual(response.status_code, 201)
                self.assertEqual(
                    response.data["status"], VideoGeneration.Status.DRAFT
                )
                generate.assert_called_once_with("Criar uma dica")
                generation = VideoGeneration.objects.get()
                self.assertEqual(generation.payload["title"], "Dica rápida")
                render.assert_not_called()

                render_response = self.client.post(
                    f"/api/v1/videos/{generation.pk}/render/",
                    {"payload": valid_payload()},
                    format="json",
                )

                self.assertEqual(render_response.status_code, 200)
                self.assertEqual(
                    render_response.data["status"], VideoGeneration.Status.COMPLETED
                )
                render.assert_called_once()
                generation.refresh_from_db()
                generation.output_file.delete(save=False)


class VideoQueueFailureApiTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="queue-failure",
            password="secure-test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @override_settings(VIDEO_RENDER_MODE="celery")
    @patch(
        "videos.services.dispatch.enqueue_task",
        side_effect=TaskQueueUnavailable("broker unavailable"),
    )
    def test_unavailable_task_broker_returns_503_and_marks_generation_failed(
        self, enqueue
    ):
        response = self.client.post(
            "/api/v1/videos/",
            {"prompt": "Criar uma dica"},
            format="json",
        )

        self.assertEqual(response.status_code, 503)
        generation = VideoGeneration.objects.get()
        self.assertEqual(generation.status, VideoGeneration.Status.FAILED)
        self.assertIn("broker unavailable", generation.error_message)
        enqueue.assert_called_once()


class VideoRenderTaskTests(TestCase):
    @patch("videos.services.generation.render_video")
    def test_successful_render_persists_file_and_status(self, render):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                user = get_user_model().objects.create_user(username="renderer")
                generation = VideoGeneration.objects.create(
                    user=user,
                    prompt="Criar uma dica",
                    payload=valid_payload(),
                )

                def write_fake_mp4(payload, destination):
                    Path(destination).write_bytes(b"fake-mp4")
                    return Path(destination)

                render.side_effect = write_fake_mp4
                result = render_video_generation(str(generation.pk))

                generation.refresh_from_db()
                self.assertEqual(result, str(generation.pk))
                self.assertEqual(generation.status, VideoGeneration.Status.COMPLETED)
                self.assertTrue(generation.output_file)
                generation.output_file.delete(save=False)

    @patch(
        "videos.services.generation.render_video",
        side_effect=RemotionRenderError("failed"),
    )
    def test_failed_render_sets_failed_status(self, render):
        user = get_user_model().objects.create_user(username="failed-renderer")
        generation = VideoGeneration.objects.create(
            user=user,
            prompt="Criar uma dica",
            payload=valid_payload(),
        )

        with self.assertLogs("videos.services.generation", level="ERROR"):
            with self.assertRaises(RemotionRenderError):
                render_video_generation(str(generation.pk))

        generation.refresh_from_db()
        self.assertEqual(generation.status, VideoGeneration.Status.FAILED)
        self.assertTrue(generation.error_message)

    @patch(
        "videos.services.generation.generate_video_payload",
        return_value=valid_payload(),
    )
    def test_script_generation_does_not_render_without_user_approval(self, generate):
        user = get_user_model().objects.create_user(username="agent-renderer")
        generation = VideoGeneration.objects.create(
            user=user,
            prompt="Cria um vídeo de boas-vindas",
            payload={},
        )

        generate_video_script(str(generation.pk))

        generation.refresh_from_db()
        self.assertEqual(generation.payload, valid_payload())
        self.assertEqual(generation.status, VideoGeneration.Status.DRAFT)
        generate.assert_called_once_with(generation.prompt)


class AgentProviderTests(TestCase):
    @patch("videos.services.agent.urlopen")
    def test_provider_payload_is_validated(self, urlopen):
        response_body = (
            b'{"choices":[{"message":{"content":"'
            b'{\\"schema_version\\":1,\\"title\\":\\"Dica\\",\\"scenes\\":'
            b'[{\\"text\\":\\"Ola\\",\\"duration_seconds\\":3,'
            b'\\"background_color\\":\\"#102030\\"}]}"}}]}'
        )
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = response_body

        with self.settings(AGENT_API_KEY="test-key", AGENT_MODEL="test-model"):
            payload = generate_video_payload("Criar uma dica")

        self.assertEqual(payload["title"], "Dica")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")

    def test_provider_requires_configuration(self):
        with self.settings(AGENT_API_KEY="", AGENT_MODEL=""):
            with self.assertRaises(AgentGenerationError):
                generate_video_payload("Criar uma dica")
