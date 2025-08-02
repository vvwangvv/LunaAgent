import asyncio
import time
import base64
import json
from typing import AsyncGenerator
from fastapi import WebSocketDisconnect
from luna_agent.utils import StreamingResampler


class WebRTCData:
    def __init__(self):
        self.ws = None
        self.resampler = None
        self.sample_rate = 16000
        self.disconnect = asyncio.Event()

    async def setup(self, user_audio_sample_rate: int, user_audio_num_channels: int = 1):
        if user_audio_sample_rate != self.sample_rate:
            self.resampler = StreamingResampler(
                in_rate=user_audio_sample_rate, out_rate=self.sample_rate, num_channels=user_audio_num_channels
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
                    chunk = self.resampler(chunk)
                yield chunk
        except WebSocketDisconnect:
            pass
        finally:
            self.disconnect.set()

    async def write(self, data: bytes | str, **params):
        if not self.ready:
            raise RuntimeError("WebSocket connection is not established")
        data_type = "text"
        if isinstance(data, bytes):
            data = base64.b64encode(data).decode("utf-8")
            data_type = "bytes"
        payload = {"data": data, "data_type": data_type, **params}
        await self.ws.send_text(json.dumps(payload))


class WebRTCEvent:
    def __init__(self):
        self.ws = None
        self.disconnect = asyncio.Event()

    async def user_interrupt(self):
        await self.send_event(
            "user_interrupt",
            {"timestamp": int(time.time() * 1000)},
        )

    async def set_avatar(self, avatar: str):
        await self.send_event("set_avatar", {"avatar": avatar})

    async def send_event(self, event: str, data: dict):
        if not self.ws:
            raise RuntimeError("WebSocket connection is not established")
        try:
            await self.ws.send_text(json.dumps({"event": event, "data": data}))
        except WebSocketDisconnect:
            self.disconnect.set()
