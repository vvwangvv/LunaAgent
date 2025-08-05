import asyncio
import time
import base64
import json
from typing import AsyncGenerator

from fastapi import WebSocketDisconnect, WebSocket
from luna_agent.utils import StreamingResampler, safe_create_task, ByteQueue
from starlette.websockets import WebSocketState
from luna_agent.utils import logger


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
                dst_rate=read_dst_sr,
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

    def flush(self):
        pass

    def clear(self):
        pass


class WebRTCDataLiveStream(WebRTCData):
    def __init__(self, chunk_ms: int = 100):
        super().__init__()
        self.chunk_ms = chunk_ms
        self.on_flush = lambda: None
        self.flushed = False
        self.buffer = ByteQueue()

    async def setup(self, write_dst_sr=16000, write_dst_channels=1, **kwargs):
        await super().setup(write_dst_sr=write_dst_sr, **kwargs)

        self.ms2bytes = lambda x: x * write_dst_sr // 1000 * 2 * write_dst_channels
        self.bytes2ms = lambda x: x * 1000 // write_dst_sr // 2 // write_dst_channels
        self.chunk_bytes = self.ms2bytes(self.chunk_ms)

    async def connect(self, websocket: WebSocket):
        logger.info(f"Connecting WebRTCDataLiveStream with chunk size {self.chunk_bytes} bytes")
        await super().connect(websocket)
        safe_create_task(self.livestream())

    async def livestream(self):
        while True:
            try:
                chunk = self.buffer.pop(self.chunk_bytes)
                if not chunk:
                    if self.flushed:
                        self.flushed = False
                        await self.on_flush()
                else:
                    logger.info(f"Sending chunk of size {len(chunk)}")
                    await super().write(chunk)
                await asyncio.sleep(self.chunk_ms / 1000)
            except WebSocketDisconnect:
                break

    def flush(self):
        """
        TODO: change the name
        indicate end of a response
        """
        self.flushed = True

    def clear(self):
        self.buffer.clear()

    async def write(self, data: bytes | str, **params):
        if isinstance(data, str):
            return await super().write(data, **params)
        self.flushed = False
        self.buffer.append(data)


class WebRTCEvent:
    def __init__(self):
        self.ws = None
        self.disconnect = asyncio.Event()

    async def connect(self, websocket: WebSocket):
        self.ws = websocket
        await self.ws.accept()

    async def send_event(self, event: str, data: dict):
        if not self.ws or self.ws.client_state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket connection is not established")
        try:
            await self.ws.send_text(json.dumps({"event": event, "data": data}))
        except WebSocketDisconnect:
            self.disconnect.set()
