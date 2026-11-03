import json
import tempfile
from urllib.error import HTTPError
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import MediaAsset, VideoGeneration
from .serializers import VideoPayloadSerializer
from .services.agent import AgentGenerationError, generate_video_payload
from .services.dispatch import TaskQueueUnavailable
from .services.generation import generate_video_script, render_video_generation
from .services.media_assets import MediaAssetError, stage_render_assets, validate_asset_ownership
from .services.narration import LocalNarrationError, generate_local_narration
from .services.remotion import RemotionRenderError
from .services.visual_assets import (
    VisualAssetError,
    _build_image_request,
    _compose_image_prompt,
    _generate_image,
    _next_seed,
    prepare_visual_assets,
)


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
        self.assertEqual(serializer.validated_data["template_id"], "showcase")

    def test_rejects_unknown_template(self):
        payload = valid_payload()
        payload["template_id"] = "unlisted_template"
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_rejects_path_traversal_in_image_path(self):
        payload = valid_payload()
        payload["scenes"][0]["image_path"] = "assets/../../private.jpg"
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_accepts_sixty_seconds_across_more_than_eight_scenes(self):
        payload = valid_payload()
        payload["scenes"] = [
            {
                "text": "Frame",
                "duration_seconds": 5,
                "background_color": "#102030",
            }
        ] * 12
        serializer = VideoPayloadSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(len(serializer.validated_data["scenes"]), 12)

    def test_rejects_total_video_duration_over_sixty_seconds(self):
        payload = valid_payload()
        payload["scenes"] = [
            {
                "text": "Frame",
                "duration_seconds": 31,
                "background_color": "#102030",
            },
            {
                "text": "Frame seguinte",
                "duration_seconds": 30,
                "background_color": "#102030",
            },
        ]

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("60 segundos", str(serializer.errors))

    def test_accepts_visual_plans_for_more_than_eight_scenes(self):
        payload = valid_payload()
        payload["scenes"] = [
            {
                "text": f"Frame {index}",
                "duration_seconds": 5,
                "background_color": "#102030",
            }
            for index in range(12)
        ]
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": index,
                    "transition": {"type": "fade"},
                }
                for index in range(12)
            ],
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            len(serializer.validated_data["visual_direction_plan"]["scenes"]),
            12,
        )

    def test_rejects_duration_beyond_remotion_safe_frame_precision(self):
        payload = valid_payload()
        payload["scenes"][0]["duration_seconds"] = (2**53 // 30) + 1

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())

    def test_accepts_schema_two_media_layers_and_narration(self):
        payload = valid_payload()
        payload["schema_version"] = 2
        payload["scenes"][0]["layers"] = [
            {
                "asset_id": "f50336e5-f2dd-44a7-a05e-3c0053dd1e4e",
                "kind": "image",
                "role": "background",
            }
        ]
        payload["narration"] = {"text": "Olá", "generate_local": True}

        serializer = VideoPayloadSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_accepts_visual_effects_and_end_card_within_sixty_seconds(self):
        payload = valid_payload()
        payload["schema_version"] = 2
        payload["scenes"][0].update(
            {
                "image_treatment": "monochrome",
                "typography_animation": "typewriter",
                "motion_graphic": "orbit",
            }
        )
        payload["end_card"] = {
            "enabled": True,
            "title": "Até breve",
            "subtitle": "Mais ideias a caminho",
            "cta": "Segue",
            "duration_seconds": 3,
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["end_card"]["duration_seconds"], 3)

    def test_rejects_end_card_that_exceeds_sixty_second_total(self):
        payload = valid_payload()
        payload["schema_version"] = 2
        payload["scenes"][0]["duration_seconds"] = 58
        payload["end_card"] = {
            "enabled": True,
            "title": "Até breve",
            "cta": "Segue",
            "duration_seconds": 3,
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("60 segundos", str(serializer.errors))

    def test_rejects_visual_effects_in_schema_one(self):
        payload = valid_payload()
        payload["scenes"][0]["image_treatment"] = "warm"

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("schema_version", serializer.errors)

    def test_rejects_media_layers_in_schema_one(self):
        payload = valid_payload()
        payload["scenes"][0]["layers"] = [
            {
                "asset_id": "f50336e5-f2dd-44a7-a05e-3c0053dd1e4e",
                "kind": "image",
                "role": "background",
            }
        ]

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())

    def test_accepts_partial_visual_direction_plan_with_safe_default(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 0,
                    "camera": {"movement": "slow_zoom"},
                }
            ],
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["visual_direction_plan"]["scenes"][0][
                "camera"
            ]["intensity"],
            1.0,
        )

    def test_accepts_and_defaults_scene_transition(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 0,
                    "camera": {"movement": "slow_zoom"},
                    "transition": {"type": "wipe_left"},
                }
            ],
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["visual_direction_plan"]["scenes"][0][
                "transition"
            ],
            {"type": "wipe_left", "duration_frames": 12},
        )

    def test_accepts_transition_without_changing_camera_motion(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 0,
                    "transition": {"type": "fade"},
                }
            ],
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn(
            "camera",
            serializer.validated_data["visual_direction_plan"]["scenes"][0],
        )

    def test_rejects_unknown_transition_and_invalid_duration(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 0,
                    "camera": {"movement": "slow_zoom"},
                    "transition": {"type": "spin"},
                }
            ],
        }
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        payload["visual_direction_plan"]["scenes"][0]["transition"] = {
            "type": "fade",
            "duration_frames": 31,
        }
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_accepts_legacy_payload_without_visual_direction_plan(self):
        serializer = VideoPayloadSerializer(data=valid_payload())

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("visual_direction_plan", serializer.validated_data)

    def test_rejects_unknown_camera_effect(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 0,
                    "camera": {"movement": "parallax_3d"},
                }
            ],
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())

    def test_rejects_camera_intensity_outside_supported_range(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 0,
                    "camera": {"movement": "slow_zoom", "intensity": 1.1},
                }
            ],
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())

    def test_rejects_camera_plan_for_missing_or_duplicate_scene(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 1,
                    "camera": {"movement": "slow_zoom"},
                }
            ],
        }
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        payload["visual_direction_plan"]["scenes"] = [
            {"scene_index": 0, "camera": {"movement": "slow_zoom"}},
            {"scene_index": 0, "camera": {"movement": "pan_left"}},
        ]
        serializer = VideoPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_rejects_unregistered_fields_in_visual_plan(self):
        payload = valid_payload()
        payload["visual_direction_plan"] = {
            "schema_version": 1,
            "theme": "cinematic_stories",
            "scenes": [
                {
                    "scene_index": 0,
                    "camera": {
                        "movement": "slow_zoom",
                        "javascript": "alert(1)",
                    },
                }
            ],
        }

        serializer = VideoPayloadSerializer(data=payload)

        self.assertFalse(serializer.is_valid())


class MediaAssetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="asset-owner")
        self.other_user = get_user_model().objects.create_user(username="asset-other")

    def create_asset(self, user=None, kind=MediaAsset.Kind.IMAGE):
        asset = MediaAsset(
            user=user or self.user,
            kind=kind,
            original_name="scene.png",
            size_bytes=5,
        )
        asset.file.save("scene.png", ContentFile(b"image"), save=True)
        return asset

    def test_stages_owner_assets_into_temporary_remotion_public_directory(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                asset = self.create_asset()
                audio_asset = MediaAsset(
                    user=self.user,
                    kind=MediaAsset.Kind.AUDIO,
                    original_name="voice.wav",
                    size_bytes=5,
                )
                audio_asset.file.save("voice.wav", ContentFile(b"audio"), save=True)
                payload = valid_payload()
                payload["schema_version"] = 2
                payload["scenes"][0]["layers"] = [
                    {
                        "asset_id": str(asset.pk),
                        "kind": "image",
                        "role": "background",
                        "motion": "slow_zoom",
                        "opacity": 1,
                        "fit": "cover",
                    }
                ]
                payload["narration"] = {"asset_id": str(audio_asset.pk)}
                remotion_dir = Path(media_root) / "remotion"

                with stage_render_assets(payload, self.user, remotion_dir) as staged:
                    layer = staged["scenes"][0]["layers"][0]
                    staged_file = remotion_dir / "public" / layer["asset_path"]
                    staged_audio = (
                        remotion_dir
                        / "public"
                        / staged["narration"]["audio_path"]
                    )
                    self.assertTrue(staged_file.is_file())
                    self.assertTrue(staged_audio.is_file())
                    self.assertNotIn("asset_id", layer)
                    self.assertNotIn("asset_id", staged["narration"])

                self.assertFalse(staged_file.exists())
                self.assertFalse(staged_audio.exists())
                asset.file.delete(save=False)
                audio_asset.file.delete(save=False)

    def test_rejects_assets_owned_by_another_user(self):
        asset = self.create_asset(user=self.other_user)
        payload = valid_payload()
        payload["scenes"][0]["layers"] = [
            {
                "asset_id": str(asset.pk),
                "kind": "image",
            }
        ]

        with self.assertRaises(MediaAssetError):
            validate_asset_ownership(payload, self.user)

        asset.file.delete(save=False)

    def test_upload_and_asset_file_are_owner_scoped(self):
        client = APIClient()
        client.force_authenticate(self.user)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = client.post(
                    "/api/v1/videos/assets/",
                    {
                        "kind": "image",
                        "file": SimpleUploadedFile("scene.png", b"image"),
                    },
                    format="multipart",
                )
                self.assertEqual(response.status_code, 201)
                asset_id = response.data["id"]
                download = client.get(
                    f"/api/v1/videos/assets/{asset_id}/file/"
                )
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download["Content-Type"], "image/png")
                self.assertEqual(b"".join(download.streaming_content), b"image")
                download.close()

                client.force_authenticate(self.other_user)
                forbidden = client.get(
                    f"/api/v1/videos/assets/{asset_id}/file/"
                )
                self.assertEqual(forbidden.status_code, 404)

                MediaAsset.objects.get(pk=asset_id).file.delete(save=False)

    def test_upload_rejects_mismatched_extension(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(
            "/api/v1/videos/assets/",
            {
                "kind": "image",
                "file": SimpleUploadedFile("movie.mp4", b"video"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


class VisualAssetPipelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="visual-asset-owner")

    def test_missing_visual_prompt_is_reported_without_failing_the_script(self):
        payload = {
            "schema_version": 2,
            "title": "História",
            "scenes": [
                {
                    "text": "A cidade acorda.",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                }
            ],
        }

        with patch("videos.services.visual_assets._save_generated_image") as generate:
            result, message = prepare_visual_assets(payload, self.user)

        self.assertIs(result, payload)
        self.assertIn("falta uma descrição visual", message)
        self.assertNotIn("layers", result["scenes"][0])
        generate.assert_not_called()

    def test_generation_request_encodes_prompt_and_sets_vertical_model_parameters(self):
        with self.settings(POLLINATIONS_API_KEY=""):
            request = _build_image_request("cinematic café à noite", 3721)

        parsed_url = urlsplit(request.full_url)
        params = parse_qs(parsed_url.query)
        self.assertEqual(parsed_url.scheme, "https")
        self.assertEqual(parsed_url.hostname, "gen.pollinations.ai")
        self.assertEqual(
            parsed_url.path,
            "/image/cinematic%20caf%C3%A9%20%C3%A0%20noite",
        )
        self.assertEqual(params["width"], ["1080"])
        self.assertEqual(params["height"], ["1920"])
        self.assertEqual(params["model"], ["black-forest-labs/flux.1-schnell"])
        self.assertEqual(params["seed"], ["3721"])
        self.assertIsNone(request.get_header("Authorization"))

    def test_generation_request_adds_optional_api_key_as_authorization_header(self):
        with self.settings(POLLINATIONS_API_KEY="test-key"):
            request = _build_image_request("a dramatic city at night", 42)

        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")

    def test_scene_prompt_combines_topic_with_shared_visual_theme(self):
        image_prompt = _compose_image_prompt(
            "A tired shop owner reviews a sudden increase in online orders",
            "Charcoal palette, amber practical lights, subtle documentary grain.",
            "cinematic_stories",
        )

        self.assertIn("Charcoal palette, amber practical lights", image_prompt)
        self.assertIn("tired shop owner", image_prompt)
        self.assertIn("distinct subject and framing", image_prompt)
        self.assertIn("no text, no logos, no watermark", image_prompt)

    def test_selected_theme_supplies_shared_direction_when_agent_omits_one(self):
        image_prompt = _compose_image_prompt(
            "A ceramic bottle on a travertine pedestal",
            "",
            "modern_product",
        )

        self.assertIn("premium softbox lighting", image_prompt)
        self.assertIn("clean negative space", image_prompt)

    @patch(
        "videos.services.visual_assets.secrets.randbelow",
        side_effect=(5, 5, 6),
    )
    def test_seed_generation_avoids_duplicates_between_scenes(self, randbelow):
        used_seeds = set()

        seeds = [_next_seed(used_seeds), _next_seed(used_seeds)]

        self.assertEqual(seeds, [5, 6])
        self.assertEqual(randbelow.call_count, 3)

    @patch("videos.services.visual_assets.build_opener")
    def test_download_accepts_valid_generated_image(self, build_opener_mock):
        response = build_opener_mock.return_value.open.return_value.__enter__.return_value
        response.geturl.return_value = (
            "https://gen.pollinations.ai/image/cinematic?model=flux"
        )
        response.headers = {"Content-Type": "image/png"}
        response.read.return_value = b"\x89PNG\r\n\x1a\nimage-data"

        downloaded = _generate_image("cinematic city", 123)

        self.assertEqual(downloaded, (".png", b"\x89PNG\r\n\x1a\nimage-data"))
        build_opener_mock.return_value.open.assert_called_once()

    def test_generation_rejects_unexpected_content_type(self):
        with patch("videos.services.visual_assets.build_opener") as build_opener_mock:
            response = (
                build_opener_mock.return_value.open.return_value.__enter__.return_value
            )
            response.geturl.return_value = "https://gen.pollinations.ai/image/prompt"
            response.headers = {"Content-Type": "text/html"}
            response.read.return_value = b"<html>not an image</html>"

            with self.assertRaisesMessage(VisualAssetError, "formato inválido"):
                _generate_image("prompt", 1)

    def test_generation_rejects_invalid_image_signature(self):
        with patch("videos.services.visual_assets.build_opener") as build_opener_mock:
            response = (
                build_opener_mock.return_value.open.return_value.__enter__.return_value
            )
            response.geturl.return_value = "https://gen.pollinations.ai/image/prompt"
            response.headers = {"Content-Type": "image/jpeg"}
            response.read.return_value = b"not-a-jpeg"

            with self.assertRaises(VisualAssetError):
                _generate_image("prompt", 1)

    def test_generation_rejects_image_above_configured_limit(self):
        with self.settings(POLLINATIONS_MAX_IMAGE_BYTES=4):
            with patch("videos.services.visual_assets.build_opener") as build_opener_mock:
                response = (
                    build_opener_mock.return_value.open.return_value.__enter__.return_value
                )
                response.geturl.return_value = (
                    "https://gen.pollinations.ai/image/prompt"
                )
                response.headers = {"Content-Type": "image/jpeg"}
                response.read.return_value = b"\xff\xd8\xffdata"

                with self.assertRaises(VisualAssetError):
                    _generate_image("prompt", 1)

    def test_generation_reports_http_error_without_exposing_provider_response(self):
        error = HTTPError(
            "https://gen.pollinations.ai/image/private-prompt",
            503,
            "Unavailable",
            {},
            None,
        )
        with patch("videos.services.visual_assets.build_opener") as build_opener_mock:
            build_opener_mock.return_value.open.side_effect = error
            with self.assertLogs("videos.services.visual_assets", level="WARNING"):
                with self.assertRaisesMessage(
                    VisualAssetError,
                    "geração automática de imagens não está disponível",
                ):
                    _generate_image("private prompt", 1)

    def test_generation_timeout_is_reported_without_exposing_prompt(self):
        with patch("videos.services.visual_assets.build_opener") as build_opener_mock:
            build_opener_mock.return_value.open.side_effect = TimeoutError()
            with self.assertLogs("videos.services.visual_assets", level="WARNING"):
                with self.assertRaisesMessage(
                    VisualAssetError,
                    "Não foi possível contactar o serviço",
                ):
                    _generate_image("private prompt", 1)

    @patch("videos.services.visual_assets._save_generated_image")
    def test_generates_and_attaches_asset_with_prompt_and_seed_metadata(
        self,
        save_generated,
    ):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                asset = MediaAsset(
                    user=self.user,
                    kind=MediaAsset.Kind.IMAGE,
                    original_name="pollinations-123.png",
                    size_bytes=5,
                    source_provider="pollinations",
                    source_url="https://gen.pollinations.ai",
                    generation_prompt="cinematic city at night",
                    generation_seed=123,
                )
                asset.file.save("pollinations-123.png", ContentFile(b"image"), save=True)
                save_generated.return_value = asset
                payload = {
                    "schema_version": 2,
                    "title": "História",
                    "scenes": [
                        {
                            "text": "A cidade acorda.",
                            "duration_seconds": 4,
                            "background_color": "#102030",
                            "visual_prompt": "cinematic city at night",
                        }
                    ],
                }

                with patch(
                    "videos.services.visual_assets._next_seed",
                    return_value=123,
                ):
                    result, message = prepare_visual_assets(payload, self.user)

                layer = result["scenes"][0]["layers"][0]
                self.assertEqual(layer["asset_id"], str(asset.pk))
                self.assertEqual(
                    layer["source_credit"],
                    "Imagem gerada com Pollinations.ai",
                )
                self.assertEqual(layer["source_url"], "https://pollinations.ai")
                self.assertIn("1 imagem(ns)", message)
                save_generated.assert_called_once_with(
                    (
                        "Shared visual direction for this entire video: "
                        "Restrained charcoal, deep olive, and warm amber palette; "
                        "motivated practical light, deep shadows, subtle film grain, "
                        "documentary lensing, atmospheric depth. "
                        "Scene-specific image: cinematic city at night "
                        "Keep the shared palette, lighting, and photographic language "
                        "consistent, but use a distinct subject and framing for this "
                        "scene. Vertical cinematic composition, no text, no logos, "
                        "no watermark."
                    ),
                    123,
                    self.user,
                    generation_id=None,
                    scene_index=1,
                )
                asset.refresh_from_db()
                self.assertEqual(asset.source_provider, "pollinations")
                self.assertEqual(asset.generation_prompt, "cinematic city at night")
                self.assertEqual(asset.generation_seed, 123)
                self.assertFalse(asset.photographer)
                self.assertFalse(asset.attribution_url)
                asset.file.delete(save=False)

    @patch("videos.services.visual_assets._save_generated_image")
    def test_does_not_replace_user_media_already_associated_with_scene(
        self,
        save_generated,
    ):
        payload = {
            "schema_version": 2,
            "title": "História",
            "scenes": [
                {
                    "text": "A cidade acorda.",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                    "visual_prompt": "a different generated visual",
                    "layers": [
                        {
                            "asset_id": "f50336e5-f2dd-44a7-a05e-3c0053dd1e4e",
                            "kind": "image",
                            "role": "background",
                        }
                    ],
                },
                {
                    "text": "Outra cena.",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                    "visual_prompt": "another generated visual",
                    "image_path": "assets/user-image.png",
                },
            ],
        }

        result, message = prepare_visual_assets(payload, self.user)

        self.assertIs(result, payload)
        self.assertEqual(len(result["scenes"][0]["layers"]), 1)
        self.assertEqual(result["scenes"][1]["image_path"], "assets/user-image.png")
        self.assertEqual(message, "")
        save_generated.assert_not_called()

    @patch("videos.services.visual_assets._save_generated_image")
    def test_provider_failure_preserves_script_and_reports_status(self, save_generated):
        save_generated.side_effect = VisualAssetError(
            "A geração automática de imagens não está disponível."
        )
        payload = {
            "schema_version": 2,
            "title": "História",
            "scenes": [
                {
                    "text": "A cidade acorda.",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                    "visual_prompt": "cinematic city at night",
                }
            ],
        }

        result, message = prepare_visual_assets(payload, self.user)

        self.assertIs(result, payload)
        self.assertIn("o guião foi preservado", message)
        self.assertNotIn("layers", result["scenes"][0])

    @patch(
        "videos.services.generation.generate_video_payload",
        return_value={
            "schema_version": 2,
            "title": "História",
            "scenes": [
                {
                    "text": "A cidade acorda.",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                    "visual_prompt": "cinematic city at night",
                }
            ],
        },
    )
    @patch(
        "videos.services.visual_assets._save_generated_image",
        side_effect=VisualAssetError("provider unavailable"),
    )
    def test_image_provider_failure_still_saves_script_as_draft(
        self,
        save_generated,
        generate,
    ):
        generation = VideoGeneration.objects.create(
            user=self.user,
            prompt="Criar uma história",
            payload={},
        )

        with self.assertLogs("videos.services.visual_assets", level="WARNING"):
            generate_video_script(str(generation.pk))

        generation.refresh_from_db()
        self.assertEqual(generation.status, VideoGeneration.Status.DRAFT)
        self.assertEqual(generation.payload["title"], "História")
        self.assertNotIn("layers", generation.payload["scenes"][0])
        self.assertIn("o guião foi preservado", generation.asset_pipeline_message)
        save_generated.assert_called_once()
        generate.assert_called_once()


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
                {
                    "prompt": "Criar uma dica",
                    "template_id": "tutorial",
                    "visual_theme_id": "kinetic_editorial",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 202)
        generation = VideoGeneration.objects.get()
        self.assertEqual(generation.user, self.user)
        self.assertEqual(generation.template_id, "tutorial")
        self.assertEqual(generation.visual_theme_id, "kinetic_editorial")
        self.assertEqual(response.data["visual_theme_id"], "kinetic_editorial")
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

        self.assertEqual(response.status_code, 403)

    def test_create_rejects_unknown_template(self):
        response = self.client.post(
            "/api/v1/videos/",
            {"prompt": "Criar uma dica", "template_id": "unlisted_template"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_create_rejects_unknown_visual_theme(self):
        response = self.client.post(
            "/api/v1/videos/",
            {
                "prompt": "Criar uma dica",
                "visual_theme_id": "unlisted_theme",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_render_rejects_media_asset_owned_by_another_user(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                generation = VideoGeneration.objects.create(
                    user=self.user,
                    prompt="Criar uma dica",
                    payload=valid_payload(),
                    status=VideoGeneration.Status.DRAFT,
                )
                asset = MediaAsset(
                    user=self.other_user,
                    kind=MediaAsset.Kind.IMAGE,
                    original_name="scene.png",
                    size_bytes=5,
                )
                asset.file.save("scene.png", ContentFile(b"image"), save=True)
                payload = valid_payload()
                payload["schema_version"] = 2
                payload["scenes"][0]["layers"] = [
                    {
                        "asset_id": str(asset.pk),
                        "kind": "image",
                        "role": "background",
                    }
                ]

                response = self.client.post(
                    f"/api/v1/videos/{generation.pk}/render/",
                    {"payload": payload},
                    format="json",
                )

                self.assertEqual(response.status_code, 400)
                generation.refresh_from_db()
                self.assertEqual(generation.status, VideoGeneration.Status.DRAFT)
                asset.file.delete(save=False)

    @patch("videos.services.generation.render_video")
    def test_render_persists_asset_uuid_as_json_string(self, render):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                generation = VideoGeneration.objects.create(
                    user=self.user,
                    prompt="Criar uma dica",
                    payload=valid_payload(),
                    status=VideoGeneration.Status.DRAFT,
                )
                asset = MediaAsset(
                    user=self.user,
                    kind=MediaAsset.Kind.IMAGE,
                    original_name="scene.png",
                    size_bytes=5,
                )
                asset.file.save("scene.png", ContentFile(b"image"), save=True)
                payload = valid_payload()
                payload["schema_version"] = 2
                payload["scenes"][0]["layers"] = [
                    {
                        "asset_id": str(asset.pk),
                        "kind": "image",
                        "role": "background",
                    }
                ]

                staged_asset_paths = []

                def write_mp4(render_payload, destination):
                    layer = render_payload["scenes"][0]["layers"][0]
                    staged_file = (
                        Path(media_root)
                        / "remotion"
                        / "public"
                        / layer["asset_path"]
                    )
                    self.assertTrue(staged_file.is_file())
                    self.assertNotIn("asset_id", layer)
                    staged_asset_paths.append(staged_file)
                    Path(destination).write_bytes(b"fake-mp4")
                    return Path(destination)

                render.side_effect = write_mp4
                with override_settings(
                    REMOTION_PROJECT_DIR=Path(media_root) / "remotion",
                    VIDEO_RENDER_MODE="inline",
                ):
                    with self.captureOnCommitCallbacks(execute=True):
                        response = self.client.post(
                            f"/api/v1/videos/{generation.pk}/render/",
                            {"payload": payload},
                            format="json",
                        )

                self.assertEqual(response.status_code, 200)
                render.assert_called_once()
                generation.refresh_from_db()
                self.assertEqual(
                    generation.status,
                    VideoGeneration.Status.COMPLETED,
                )
                self.assertEqual(
                    generation.payload["scenes"][0]["layers"][0]["asset_id"],
                    str(asset.pk),
                )
                self.assertEqual(len(staged_asset_paths), 1)
                self.assertFalse(staged_asset_paths[0].exists())
                generation.output_file.delete(save=False)
                asset.file.delete(save=False)


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
                    {
                        "prompt": "Criar uma dica",
                        "template_id": "tutorial",
                        "visual_theme_id": "modern_product",
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, 201)
                self.assertEqual(
                    response.data["status"], VideoGeneration.Status.DRAFT
                )
                generate.assert_called_once_with(
                    "Criar uma dica",
                    template_id="tutorial",
                    visual_theme_id="modern_product",
                    generation_id=str(VideoGeneration.objects.get().pk),
                )
                generation = VideoGeneration.objects.get()
                self.assertEqual(generation.payload["title"], "Dica rápida")
                self.assertEqual(generation.payload["template_id"], "tutorial")
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
                self.assertEqual(
                    render_response.data["visual_theme_id"], "modern_product"
                )
                render.assert_called_once()
                self.assertEqual(render.call_args.args[0]["template_id"], "tutorial")
                self.assertEqual(
                    render.call_args.args[0]["visual_theme_id"], "modern_product"
                )
                generation.refresh_from_db()

                rerender_response = self.client.post(
                    f"/api/v1/videos/{generation.pk}/render/",
                    {
                        "payload": valid_payload(),
                        "visual_theme_id": "kinetic_editorial",
                    },
                    format="json",
                )
                self.assertEqual(rerender_response.status_code, 200)
                self.assertEqual(
                    rerender_response.data["visual_theme_id"], "kinetic_editorial"
                )
                self.assertEqual(render.call_count, 2)
                self.assertEqual(
                    render.call_args.args[0]["visual_theme_id"],
                    "kinetic_editorial",
                )
                generation.refresh_from_db()
                self.assertEqual(generation.visual_theme_id, "kinetic_editorial")
                self.assertEqual(len(list(Path(media_root).rglob("*.mp4"))), 1)

                unchanged_response = self.client.post(
                    f"/api/v1/videos/{generation.pk}/render/",
                    {
                        "payload": valid_payload(),
                        "visual_theme_id": "kinetic_editorial",
                    },
                    format="json",
                )
                self.assertEqual(unchanged_response.status_code, 400)
                self.assertEqual(render.call_count, 2)
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
    def test_unavailable_task_broker_returns_created_generation_as_failed(
        self, enqueue
    ):
        with self.assertLogs("videos", level="INFO") as captured_logs:
            response = self.client.post(
                "/api/v1/videos/",
                {"prompt": "Criar uma dica"},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        generation = VideoGeneration.objects.get()
        self.assertEqual(generation.status, VideoGeneration.Status.FAILED)
        self.assertIn("broker unavailable", generation.error_message)
        self.assertEqual(response.data["id"], str(generation.pk))
        self.assertEqual(response.data["status"], VideoGeneration.Status.FAILED)
        self.assertIn("broker unavailable", response.data["error_message"])
        enqueue.assert_called_once()
        log_output = "\n".join(captured_logs.output)
        self.assertIn("generation_stage=request_received", log_output)
        self.assertIn("generation_stage=persisted", log_output)
        self.assertIn("generation_stage=dispatch_failed", log_output)
        self.assertIn("generation_stage=response_ready", log_output)
        self.assertIn(str(generation.pk), log_output)


class VideoRenderTaskTests(TestCase):
    @patch("videos.services.visual_assets._generate_image")
    @patch("videos.services.agent.urlopen")
    def test_three_distinct_briefings_keep_scene_direction_and_save_local_images(
        self,
        agent_urlopen,
        generate_image,
    ):
        user = get_user_model().objects.create_user(username="three-briefing-creator")
        cases = [
            (
                "Como a inteligência artificial está a transformar os negócios.",
                "Inteligência artificial",
                [
                    ("Automação começa nos bastidores.", "Robotic arms sort packages in a small warehouse"),
                    ("Dados revelam novas oportunidades.", "Shop owner studies luminous sales charts after closing"),
                ],
            ),
            (
                "Como proteger os oceanos da poluição.",
                "Oceanos mais limpos",
                [
                    ("O plástico começa em terra.", "Plastic bottles wash from a storm drain into the sea"),
                    ("A vida marinha sente o impacto.", "Sea turtle swims through a drifting plastic bag"),
                ],
            ),
            (
                "Como preparar uma refeição saudável em casa.",
                "Cozinhar com equilíbrio",
                [
                    ("Ingredientes simples fazem diferença.", "Hands slice fresh vegetables on a wooden board"),
                    ("O prato ganha cor e sabor.", "Balanced colorful meal served beside a sunny kitchen window"),
                ],
            ),
        ]
        agent_responses = []
        expected_directions = []
        for _briefing, title, scenes in cases:
            direction = (
                "Consistent charcoal shadows, warm amber practical light, "
                "documentary lensing and subtle film grain."
            )
            expected_directions.append(direction)
            payload = {
                "schema_version": 2,
                "title": title,
                "visual_direction": direction,
                "scenes": [
                    {
                        "text": text,
                        "duration_seconds": 4,
                        "background_color": "#102030",
                        "visual_prompt": visual_prompt,
                    }
                    for text, visual_prompt in scenes
                ],
            }
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                {
                    "choices": [
                        {"message": {"content": json.dumps(payload)}},
                    ]
                }
            ).encode("utf-8")
            agent_responses.append(response)

        agent_urlopen.side_effect = agent_responses
        generate_image.return_value = (".jpg", b"\xff\xd8\xfftest-image")

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                MEDIA_ROOT=media_root,
                AGENT_API_KEY="test-agent-key",
                AGENT_MODEL="test-agent-model",
            ):
                generations = [
                    VideoGeneration.objects.create(
                        user=user,
                        prompt=briefing,
                        payload={},
                    )
                    for briefing, _title, _scenes in cases
                ]
                for generation in generations:
                    generate_video_script(str(generation.pk))

                generated_prompts = []
                for generation in generations:
                    generation.refresh_from_db()
                    self.assertEqual(generation.status, VideoGeneration.Status.DRAFT)
                    self.assertEqual(len(generation.payload["scenes"]), 2)
                    self.assertTrue(generation.payload["visual_direction"])
                    for scene in generation.payload["scenes"]:
                        layer = scene["layers"][0]
                        asset = MediaAsset.objects.get(pk=layer["asset_id"])
                        self.assertEqual(asset.source_provider, "pollinations")
                        self.assertTrue(asset.generation_seed is not None)
                        self.assertIn(
                            generation.payload["visual_direction"],
                            asset.generation_prompt,
                        )
                        generated_prompts.append(asset.generation_prompt)
                        asset.file.delete(save=False)

                self.assertEqual(generate_image.call_count, 6)
                self.assertEqual(len(set(generated_prompts)), 6)
                self.assertNotEqual(cases[0][1], cases[1][1])
                self.assertNotEqual(cases[1][1], cases[2][1])

    @patch("videos.services.generation.prepare_visual_assets")
    @patch(
        "videos.services.generation.generate_video_payload",
        return_value={
            "schema_version": 2,
            "title": "Dica rápida",
            "scenes": [
                {
                    "text": "Uma dica",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                    "visual_prompt": "business at night",
                }
            ],
        },
    )
    def test_script_generation_runs_visual_asset_pipeline(
        self,
        generate,
        prepare_assets,
    ):
        user = get_user_model().objects.create_user(username="asset-pipeline-agent")
        payload = {
            "schema_version": 2,
            "title": "Dica rápida",
            "scenes": [
                {
                    "text": "Uma dica",
                    "duration_seconds": 4,
                    "background_color": "#102030",
                    "visual_prompt": "business at night",
                }
            ],
        }
        prepare_assets.return_value = (payload, "Imagem associada.")
        generation = VideoGeneration.objects.create(
            user=user,
            prompt="Criar uma dica",
            payload={},
        )

        with self.assertLogs("videos.services.generation", level="INFO") as logs:
            generate_video_script(str(generation.pk))

        generation.refresh_from_db()
        prepare_assets.assert_called_once()
        self.assertEqual(
            prepare_assets.call_args.args[0]["scenes"],
            payload["scenes"],
        )
        self.assertEqual(prepare_assets.call_args.args[1], user)
        self.assertEqual(generation.asset_pipeline_message, "Imagem associada.")
        self.assertEqual(generation.status, VideoGeneration.Status.DRAFT)
        log_output = "\n".join(logs.output)
        self.assertIn("generation_stage=visual_assets_started", log_output)
        self.assertIn("generation_stage=script_persisted", log_output)
        self.assertIn(str(generation.pk), log_output)

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
                self.assertEqual(
                    render.call_args.args[0]["visual_theme_id"],
                    "cinematic_stories",
                )
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

    @override_settings(PIPER_MODEL_PATH="")
    def test_local_narration_fails_clearly_without_configured_model(self):
        with self.assertRaisesMessage(LocalNarrationError, "PIPER_MODEL_PATH"):
            generate_local_narration("Texto", Path("unused.wav"))

    @patch(
        "videos.services.generation.generate_video_payload",
        return_value=valid_payload(),
    )
    def test_script_generation_does_not_render_without_user_approval(self, generate):
        user = get_user_model().objects.create_user(username="agent-renderer")
        generation = VideoGeneration.objects.create(
            user=user,
            prompt="Cria um vídeo de boas-vindas",
            template_id="brand_story",
            payload={},
        )

        with self.assertLogs("videos.services.generation", level="INFO") as logs:
            generate_video_script(str(generation.pk))

        generation.refresh_from_db()
        expected_payload = valid_payload()
        expected_payload["template_id"] = "brand_story"
        self.assertEqual(generation.payload, expected_payload)
        self.assertEqual(generation.status, VideoGeneration.Status.DRAFT)
        log_output = "\n".join(logs.output)
        self.assertIn("generation_stage=agent_started", log_output)
        self.assertIn("generation_stage=script_persisted", log_output)
        self.assertIn(str(generation.pk), log_output)
        generate.assert_called_once_with(
            generation.prompt,
            template_id="brand_story",
            visual_theme_id="cinematic_stories",
            generation_id=str(generation.pk),
        )


class AgentProviderTests(TestCase):
    @patch("videos.services.agent.urlopen")
    def test_provider_payload_is_validated(self, urlopen):
        response_body = (
            b'{"choices":[{"message":{"content":"'
            b'{\\"schema_version\\":2,\\"title\\":\\"Dica\\",'
            b'\\"visual_direction\\":\\"charcoal and amber documentary palette\\",'
            b'\\"scenes\\":[{\\"text\\":\\"Ola\\",\\"duration_seconds\\":3,'
            b'\\"background_color\\":\\"#102030\\",'
            b'\\"visual_prompt\\":\\"A baker opens a warm-lit bakery at dawn\\"}]}'
            b'"}}]}'
        )
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = response_body

        with self.settings(AGENT_API_KEY="test-key", AGENT_MODEL="test-model"):
            payload = generate_video_payload(
                "Criar uma dica",
                template_id="tutorial",
                visual_theme_id="cinematic_stories",
            )

        self.assertEqual(payload["title"], "Dica")
        self.assertEqual(
            payload["visual_direction"],
            "charcoal and amber documentary palette",
        )
        self.assertEqual(payload["template_id"], "tutorial")
        request = urlopen.call_args.args[0]
        sent_body = json.loads(request.data)
        self.assertIn("Tutorial rápido", sent_body["messages"][0]["content"])
        self.assertIn("Cinematic Stories", sent_body["messages"][0]["content"])
        self.assertIn("visual_direction", sent_body["messages"][0]["content"])
        self.assertIn("distinct subject", sent_body["messages"][0]["content"])
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")

    @patch("videos.services.agent.urlopen")
    def test_retries_invalid_agent_payload_and_accepts_long_script(self, urlopen):
        invalid_payload = {
            "schema_version": 2,
            "title": "Factos históricos",
            "scenes": [
                {
                    "text": f"Facto {index}",
                    "duration_seconds": 0,
                    "background_color": "#102030",
                    "visual_prompt": f"A distinct cinematic scene for fact {index}",
                    "motion": "slow_zoom",
                }
                for index in range(1, 13)
            ],
        }
        corrected_payload = {
            "schema_version": 2,
            "title": "Factos históricos",
            "scenes": [
                {
                    "text": f"Facto histórico {index}",
                    "duration_seconds": 5,
                    "background_color": "#102030",
                    "visual_prompt": f"A cinematic scene for historic fact {index}",
                    "motion": "slow_zoom",
                }
                for index in range(1, 13)
            ],
        }

        def provider_response(payload):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                {"choices": [{"message": {"content": json.dumps(payload)}}]}
            ).encode("utf-8")
            return response

        urlopen.side_effect = [
            provider_response(invalid_payload),
            provider_response(corrected_payload),
        ]

        with self.settings(AGENT_API_KEY="test-key", AGENT_MODEL="test-model"):
            result = generate_video_payload("12 factos históricos sobre a Grécia")

        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(len(result["scenes"]), 12)
        self.assertEqual(sum(scene["duration_seconds"] for scene in result["scenes"]), 60)
        self.assertFalse(result["end_card"]["enabled"])
        retry_body = json.loads(urlopen.call_args_list[1].args[0].data)
        retry_system_prompt = retry_body["messages"][0]["content"]
        self.assertIn("no máximo 60 segundos", retry_system_prompt)
        self.assertIn("scenes", retry_system_prompt)

    def test_provider_requires_configuration(self):
        with self.settings(AGENT_API_KEY="", AGENT_MODEL=""):
            with self.assertRaises(AgentGenerationError):
                generate_video_payload("Criar uma dica")
