import logging
import subprocess
import wave
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


class LocalNarrationError(RuntimeError):
    pass


def generate_local_narration(text, destination):
    model_path = settings.PIPER_MODEL_PATH
    if not model_path:
        raise LocalNarrationError(
            "Para gerar voz local, configure PIPER_MODEL_PATH com um modelo Piper instalado."
        )
    model = Path(model_path).resolve()
    if not model.is_file():
        raise LocalNarrationError(
            "O modelo de voz Piper configurado não foi encontrado no servidor."
        )

    try:
        result = subprocess.run(
            [
                settings.PIPER_EXECUTABLE,
                "--model",
                str(model),
                "--output_file",
                str(destination),
            ],
            input=text,
            encoding="utf-8",
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.PIPER_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Local Piper narration generation timed out")
        raise LocalNarrationError("A geração local da narração excedeu o tempo limite.") from exc
    except OSError as exc:
        logger.exception("Could not start the configured Piper executable")
        raise LocalNarrationError(
            "Não foi possível iniciar Piper. Confirme a instalação de piper-tts."
        ) from exc

    if result.returncode != 0:
        logger.error(
            "Piper failed (exit %s): %s",
            result.returncode,
            result.stderr[-2000:],
        )
        raise LocalNarrationError("O Piper não conseguiu gerar a narração.")
    if not Path(destination).is_file() or Path(destination).stat().st_size == 0:
        raise LocalNarrationError("O Piper terminou sem produzir um ficheiro de áudio.")

    try:
        with wave.open(str(destination), "rb") as audio_file:
            if audio_file.getnframes() == 0 or audio_file.getframerate() == 0:
                raise wave.Error("Empty audio stream")
    except (wave.Error, EOFError) as exc:
        raise LocalNarrationError(
            "O Piper produziu um ficheiro WAV inválido."
        ) from exc
    return Path(destination)
