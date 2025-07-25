import websockets
import numpy as np
import soxr
import base64
import json
from typing import AsyncGenerator, Tuple


class WebRTCAudio:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ws = None
        self.resampler = None
        self.sample_rate = 16000

    async def setup(self, user_audio_sample_rate: int):
        self.ws = await websockets.connect(self.base_url)
        if user_audio_sample_rate != self.sample_rate:
            self.resampler = soxr.Resampler(
                channels=1,
                in_rate=user_audio_sample_rate,
                out_rate=16000,
                quality="HQ",
            )

    async def read(self) -> AsyncGenerator[bytes, None]:
        async for message in self.ws:
            message = json.loads(message)
            chunk = base64.b64decode(message["data"].encode("utf-8"))
            if self.resampler:
                chunk = self.resample_bytes(chunk)
            yield chunk

    async def write(self, audio: bytes, response_id: str):
        payload = {
            "response_id": response_id,
            "data": base64.b64encode(audio).decode("utf-8"),
        }
        await self.ws.write(json.dumps(payload))

    def resample_bytes(self, audio: bytes) -> bytes:
        """Stateful chunk-wise resample with soxr."""
        if self.resampler is None:
            return audio
        audio = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        audio = self.resampler.process(audio)
        audio = (np.clip(audio, -1.0, 1.0) * 32768.0).astype(np.int16)
        return audio.tobytes()


class WebRTCEvent:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ws = None

    async def setup(self):
        self.ws = await websockets.connect(self.base_url)

    async def start_session(self, session_id):
        await self.ws.send(
            json.dumps(
                {
                    "event": "start_session",
                    "data": {"session_id": session_id},
                }
            )
        )

    async def set_agent_can_speak(self, agent_can_speak: bool):
        await self.ws.send(
            json.dumps(
                {
                    "event": "set_agent_can_speak",
                    "data": {"agent_can_speak": agent_can_speak},
                }
            )
        )

    async def set_avatar(self, avatar: str):
        await self.ws.send(
            json.dumps(
                {
                    "event": "set_avatar",
                    "data": {"avatar": avatar},
                }
            )
        )
