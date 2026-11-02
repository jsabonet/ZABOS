import json
import logging
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


class RemotionRenderError(RuntimeError):
    pass


def render_video(payload, destination):
    project_dir = settings.REMOTION_PROJECT_DIR
    render_script = project_dir / "scripts" / "render.cjs"
    if not render_script.is_file():
        raise RemotionRenderError("O script de renderização Remotion não foi encontrado.")

    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="video-props-",
        dir=destination.parent,
        delete=False,
    ) as props_file:
        json.dump(payload, props_file, ensure_ascii=False)
        props_path = Path(props_file.name)

    command = [
        settings.NODE_EXECUTABLE,
        str(render_script),
        "--props",
        str(props_path),
        "--output",
        str(destination),
    ]

    try:
        result = subprocess.run(
            command,
            cwd=project_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.REMOTION_RENDER_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Remotion render timed out for %s", destination.name)
        raise RemotionRenderError("A renderização excedeu o tempo limite.") from exc
    except OSError as exc:
        logger.exception("Could not start Remotion renderer")
        raise RemotionRenderError("Não foi possível iniciar o renderizador Remotion.") from exc
    finally:
        props_path.unlink(missing_ok=True)

    if result.returncode != 0:
        logger.error(
            "Remotion failed (exit %s): %s",
            result.returncode,
            (result.stderr or result.stdout)[-4000:],
        )
        raise RemotionRenderError("O Remotion terminou com erro durante a renderização.")

    if not destination.is_file() or destination.stat().st_size == 0:
        raise RemotionRenderError("O Remotion terminou sem produzir um ficheiro MP4 válido.")

    return destination
