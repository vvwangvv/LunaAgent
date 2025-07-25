import websockets
import json
from typing import AsyncGenerator, Tuple


class VAD:
    def __init__(self, base_url: str, left_pad_ms: int = 1000, unvoiced_ms_to_eot: int = 1000):
        self.base_url = base_url
        self.start = self.end = self.current = -1
        self.ws = None
        self.data = b""
        self.left_pad_samples = left_pad_ms * 16 // 1000
        self.unvoiced_samples_to_eot = unvoiced_ms_to_eot * 16 // 1000

    async def setup(self):
        self.ws = await websockets.connect(self.base_url)

    async def __call__(self, chunk: bytes) -> AsyncGenerator[Tuple[bool, bytes], None]:
        """
        Process audio chunk and yield user speech
        :param chunk: Audio chunk in bytes
        :return: Generator yielding tuples of (is_user_speaking, user_speech)
        """
        self.data += chunk
        async for message in self.ws:
            message = json.loads(message)
            start = message.get("start", self.start)
            end = message.get("end", self.end)
            current = message.get("current", current)
            if end > start:
                if (start, end) != (self.start, self.end):
                    self.start, self.end = start, end
                    user_speech: bytes = self.data[max(0, start - self.left_pad_samples) * 2 : end * 2]
                    yield (False, user_speech)
            elif current - start > self.unvoiced_samples_to_eot:
                yield (True, None)
