import asyncio
import soxr
import numpy as np
import io
import soundfile as sf
import base64
import asyncio
import logging
import numpy as np
from collections import deque

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


class AsyncTaskMixin:
    def __init__(self):
        self.tasks = {}

    def create_task(self, coro, *, name=None):
        task = safe_create_task(coro, name=name)
        self.tasks[id(task)] = task
        task.add_done_callback(lambda t: self.tasks.pop(id(t), None))
        return task

    def destroy(self):
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        self.tasks.clear()


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


class StreamingResampler:
    def __init__(self, src_rate, dst_rate, src_channels=1, dst_channels=1, block_size_ms=100):
        self.src_rate = src_rate
        self.src_channels = src_channels
        self.dst_rate = dst_rate
        self.block_size_bytes = int((block_size_ms / 1000) * src_rate * 2) * src_channels
        self.buffer = b""

    def __call__(self, chunk: bytes, end=False) -> bytes:
        self.buffer += chunk
        if end:
            buffer, self.buffer = self.buffer, b""
        else:
            num_blocks = len(self.buffer) // self.block_size_bytes
            if num_blocks == 0:
                return b""
            buffer, self.buffer = (
                self.buffer[: num_blocks * self.block_size_bytes],
                self.buffer[num_blocks * self.block_size_bytes :],
            )
        samples = (np.frombuffer(buffer, dtype=np.int16) / 32768).astype(np.float32).reshape(-1, self.num_channels)
        if self.num_channels > 1:
            samples = samples.mean(axis=1, keepdims=True)
        resampled = soxr.resample(samples, self.src_rate, self.dst_rate)
        resampled_int16 = (np.clip(resampled, -1.0, 1.0) * 32768).astype(np.int16)
        return resampled_int16.tobytes()


class ByteQueue:
    def __init__(self):
        self._dq = deque()

    def append(self, data: bytes | bytearray):
        self._dq.extend(data)

    def pop(self, n: int) -> bytes:
        return bytes(self._dq.popleft() for _ in range(min(n, len(self._dq))))

    def peek(self, n: int) -> bytes:
        return bytes([self._dq[i] for i in range(min(n, len(self._dq)))])

    def __len__(self):
        return len(self._dq)

    def clear(self):
        self._dq.clear()

    def to_bytes(self):
        return bytes(self._dq)
