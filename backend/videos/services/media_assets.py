import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from videos.models import MediaAsset


class MediaAssetError(RuntimeError):
    pass


def collect_asset_ids(payload):
    asset_ids = set()
    for scene in payload.get("scenes", []):
        for layer in scene.get("layers", []):
            if layer.get("asset_id"):
                asset_ids.add(str(layer["asset_id"]))
    narration = payload.get("narration", {})
    if narration.get("asset_id"):
        asset_ids.add(str(narration["asset_id"]))
    return asset_ids


def validate_asset_ownership(payload, user):
    asset_ids = collect_asset_ids(payload)
    if not asset_ids:
        return
    assets = {
        str(asset.pk): asset
        for asset in MediaAsset.objects.filter(pk__in=asset_ids, user=user)
    }
    if assets.keys() != asset_ids:
        raise MediaAssetError(
            "Um ou mais ficheiros não existem ou não pertencem a este utilizador."
        )

    for scene in payload.get("scenes", []):
        for layer in scene.get("layers", []):
            asset = assets.get(str(layer.get("asset_id")))
            if asset and asset.kind != layer["kind"]:
                raise MediaAssetError(
                    "O tipo de um ficheiro não corresponde à camada seleccionada."
                )
    narration = payload.get("narration", {})
    narration_asset = assets.get(str(narration.get("asset_id")))
    if narration_asset and narration_asset.kind != MediaAsset.Kind.AUDIO:
        raise MediaAssetError("A narração tem de usar um ficheiro de áudio.")


@contextmanager
def stage_render_assets(
    payload,
    user,
    remotion_project_dir,
    generated_audio_path=None,
):
    validate_asset_ownership(payload, user)
    asset_ids = collect_asset_ids(payload)
    assets = {
        str(asset.pk): asset
        for asset in MediaAsset.objects.filter(pk__in=asset_ids, user=user)
    }
    if not assets and not generated_audio_path:
        yield payload
        return

    public_assets = Path(remotion_project_dir) / "public" / "assets"
    public_assets.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"render-{uuid4().hex}-",
        dir=public_assets,
    ) as staged_directory:
        staged_root = Path(staged_directory)

        def copy_asset(asset_id):
            asset = assets[str(asset_id)]
            target = staged_root / f"{asset.pk}{Path(asset.file.name).suffix.lower()}"
            with asset.file.open("rb") as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            return target.relative_to(public_assets).as_posix()

        for scene in payload.get("scenes", []):
            for layer in scene.get("layers", []):
                layer["asset_path"] = f"assets/{copy_asset(layer['asset_id'])}"
                layer.pop("asset_id")
        narration = payload.get("narration", {})
        if narration.get("asset_id"):
            narration["audio_path"] = f"assets/{copy_asset(narration['asset_id'])}"
            narration.pop("asset_id")
        if generated_audio_path:
            target = staged_root / "narration.wav"
            shutil.copyfile(generated_audio_path, target)
            narration["audio_path"] = (
                f"assets/{target.relative_to(public_assets).as_posix()}"
            )
            narration.pop("generate_local", None)

        yield payload
