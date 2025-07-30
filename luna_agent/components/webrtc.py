import asyncio
import numpy as np
import soxr
import base64
import json
from typing import AsyncGenerator
from fastapi import WebSocketDisconnect


class WebRTCAudio:
    def __init__(self):
        self.ws = None
        self.resampler = None
        self.sample_rate = 16000
        self.disconnect = asyncio.Event()

    async def setup(self, user_audio_sample_rate: int):
        if user_audio_sample_rate != self.sample_rate:
            self.resampler = soxr.Resampler(
                channels=1,
                in_rate=user_audio_sample_rate,
                out_rate=16000,
                quality="HQ",
            )
    
    @property
    def ready(self):
        return self.ws is not None

    async def read(self) -> AsyncGenerator[bytes, None]:
        if not self.ready:
            raise RuntimeError("WebSocket connection is not established")
        try:
            while True:
                chunk = await self.ws.receive_bytes()
                if self.resampler:
                    chunk = self.resample_bytes(chunk)
                yield chunk
        except WebSocketDisconnect:
            pass
        finally:
            self.disconnect.set()

    async def write(self, audio: bytes, response_id: str):
        if not self.ready:
            raise RuntimeError("WebSocket connection is not established")
        payload = {
            "response_id": response_id,
            "data": base64.b64encode(audio).decode("utf-8"),
        }
        await self.ws.send_text(json.dumps(payload))

    def resample_bytes(self, audio: bytes) -> bytes:
        """Stateful chunk-wise resample with soxr."""
        if self.resampler is None:
            return audio
        audio = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        audio = self.resampler.process(audio)
        audio = (np.clip(audio, -1.0, 1.0) * 32768.0).astype(np.int16)
        return audio.tobytes()


class WebRTCEvent:
    def __init__(self):
        self.ws = None
        self.disconnect = asyncio.Event()

    async def set_agent_can_speak(self, agent_can_speak: bool):
        await self.send_event("set_agent_can_speak", {"agent_can_speak": agent_can_speak})

    async def set_avatar(self, avatar: str):
        await self.send_event("set_avatar", {"avatar": avatar})

    async def send_event(self, event: str, data: dict):
        if not self.ws:
            raise RuntimeError("WebSocket connection is not established")
        try:
            await self.ws.send_text( json.dumps( { "event": event, "data": data }))
        except WebSocketDisconnect:
            self.disconnect.set()
