import asyncio
import numpy as np
import io
import soundfile as sf
import base64
import asyncio
import logging
import numpy as np

logger = logging.getLogger("luna_agent")


def pcm2base64(audio: bytes, sample_rate: int = 16000):
    audio: bytes = pcm2wav(audio, sample_rate)
    audio_base64 = base64.b64encode(audio).decode("utf-8")
    return audio_base64


def pcm2wav(pcm_bytes, sample_rate=16000):
    """
    add wav header to pcm bytes
    """
    buffer = io.BytesIO()
    audio = np.frombuffer(pcm_bytes, dtype=np.int16)
    sf.write(buffer, audio, samplerate=sample_rate, format="wav")
    buffer.seek(0)
    return buffer.getvalue()


def safe_create_task(coro, *, name=None):
    task = asyncio.create_task(coro, name=name)

    def _handle_result(task: asyncio.Task):
        try:
            exc = task.exception()
            if exc is not None:
                logger.exception("Unhandled exception in background task", exc_info=exc)
        except asyncio.CancelledError:
            logger.info("Background task was cancelled")

    task.add_done_callback(_handle_result)
    return task


def format_msg(content):
    fmt = ""
    for c in content:
        if isinstance(c, dict):
            if "input_audio" in c:
                fmt += f"[audio]({c['id']})"
            else:
                fmt += c["text"]
        else:
            fmt += c

    return fmt
