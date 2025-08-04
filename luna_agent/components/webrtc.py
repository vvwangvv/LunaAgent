import asyncio
import time
import base64
import json
from typing import AsyncGenerator
from fastapi import WebSocketDisconnect, WebSocket, WebSocketState
from luna_agent.utils import StreamingResampler, safe_create_task, ByteQueue


class WebRTCData:
    def __init__(
        self,
    ):
        self.ws = None
        self.read_resampler = None
        self.write_resampler = None
        self.disconnect = asyncio.Event()

    async def setup(
        self,
        read_src_sr: int = 16000,
        read_dst_sr: int = 16000,
        write_src_sr: int = 16000,
        write_dst_sr: int = 16000,
        read_src_channels: int = 1,
        read_dst_channels: int = 1,
        write_src_channels: int = 1,
        write_dst_channels: int = 1,
    ):
        if read_src_sr != read_dst_sr or read_src_channels != read_dst_channels:
            self.read_resampler = StreamingResampler(
                src_rate=read_src_sr,
                src_rate=read_dst_sr,
                src_channels=read_src_channels,
                dst_channels=read_dst_channels,
            )

        if write_src_sr != write_dst_sr or write_src_channels != write_dst_channels:
            self.write_resampler = StreamingResampler(
                src_rate=write_src_sr,
                dst_rate=write_dst_sr,
                src_num_channels=write_src_channels,
                dst_num_channels=write_dst_channels,
            )

    @property
    def ready(self) -> bool:
        return self.ws is not None and self.ws.client_state == WebSocketState.CONNECTED

    async def connect(self, websocket: WebSocket):
        self.ws = websocket
        await self.ws.accept()

    async def read(self) -> AsyncGenerator[bytes, None]:
        if not self.ready:
            raise RuntimeError("WebSocket connection is not established")
        try:
            while True:
                chunk = await self.ws.receive_bytes()
                if self.read_resampler:
                    chunk = self.read_resampler(chunk)
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
            if self.write_resampler:
                data = self.write_resampler(data)
            data = base64.b64encode(data).decode("utf-8")
            data_type = "bytes"
        payload = {"data": data, "data_type": data_type, **params}
        await self.ws.send_text(json.dumps(payload))


class WebRTCDataLiveStream(WebRTCData):
    def __init__(self, chunk_ms: int = 50):
        super().__init__()
        self.chunk_ms = chunk_ms
        self.on_flush = lambda: None
        self.flushed = False
        self.buffer = ByteQueue()

    async def setup(self, write_dst_sr=16000, write_dst_channels=1, **kwargs):
        await super().setup(write_dst_sr=write_dst_sr, **kwargs)

        self.bytes2ms = lambda x: x * write_dst_sr // 1000 * 2 * write_dst_channels
        self.ms2bytes = lambda x: x * 1000 // write_dst_sr // 2 // write_dst_channels
        self.chunk_bytes = self.ms2bytes(self.chunk_ms)

    async def connect(self, websocket: WebSocket):
        await super().connect(websocket)
        safe_create_task(self.livestream())

    async def livestream(self):
        while True:
            try:
                chunk = self.buffer.peak(self.chunk_bytes)
                if not chunk:
                    if self.flushed:
                        await self.on_flush()
                        self.flushed = False
                        continue
                    await asyncio.sleep(self.chunk_ms / 1000)

                await self.ws.write(chunk)
                await asyncio.sleep(self.bytes2ms(len(chunk)) / 1000)
                super().write(chunk)
            except WebSocketDisconnect:
                break

    def flush(self):
        self.flushed = True

    async def write(self, data: bytes | str, **params):
        self.flushed = False
        if isinstance(data, str):
            return await super().write(data, **params)
        self.buffer.push(data)


class WebRTCEvent:
    def __init__(self):
        self.ws = None
        self.disconnect = asyncio.Event()

    async def send_event(self, event: str, data: dict):
        if not self.ws:
            raise RuntimeError("WebSocket connection is not established")
        try:
            await self.ws.send_text(json.dumps({"event": event, "data": data}))
        except WebSocketDisconnect:
            self.disconnect.set()
