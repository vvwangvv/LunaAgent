import websockets
import json
from typing import AsyncGenerator, Tuple
from luna_agent.utils import logger


class VAD:
    def __init__(self, base_url: str, left_pad_ms: int = 300, voiced_ms_to_interrupt: int = 1000):
        self.base_url = base_url
        self.start = self.end = 0
        self.ws = None
        self.data = b""
        self.left_pad_samples = left_pad_ms * 16
        self.voiced_samples_to_interrupt = voiced_ms_to_interrupt * 16

    async def setup(self):
        self.ws = await websockets.connect(self.base_url)

    async def __call__(self, chunk: bytes) -> AsyncGenerator[Tuple[bool, bytes], None]:
        self.data += chunk
        await self.ws.send(chunk)

    async def results(self) -> AsyncGenerator[Tuple[bool, bytes], None]:
        current = -1
        async for message in self.ws:
            message = json.loads(message)
            start = message.get("start", self.start)
            end = message.get("end", self.end)
            current = message.get("current", current)

            # logger.info(f"VAD result: start={start}, end={end}, current={current}, len(data)={len(self.data)}")

            if start > end:  # user is speaking
                if end != 0 and current - start > self.voiced_samples_to_interrupt:
                    yield (True, None)
            else:
                if (start, end) != (self.start, self.end):
                    user_speech: bytes = self.data[max(0, start - self.left_pad_samples) * 2 : end * 2]
                    yield (False, user_speech)
            self.start, self.end = start, end
