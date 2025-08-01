import base64
import asyncio
import json
from typing import AsyncGenerator, Tuple
from luna_agent.utils import StreamingResampler


class Echo:
    def __init__(self):
        self.resampler = None
        self.buffer = b""

    async def setup(self):
        pass

    async def __call__(self, chunk: bytes) -> AsyncGenerator[Tuple[bool, bytes], None]:
        self.buffer += chunk

    async def results(self) -> AsyncGenerator[Tuple[bool, bytes], None]:
        while True:
            if len(self.buffer) == 0:
                await asyncio.sleep(0)
                continue
            buffer, self.buffer = self.buffer, b""
            yield buffer
