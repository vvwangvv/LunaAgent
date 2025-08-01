import base64
import websockets
import json
from typing import AsyncGenerator, Tuple
from luna_agent.utils import StreamingResampler


class Interpret:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session_id = None
        self.ws = None
        self.resampler = None
        self.target_language = None

    async def setup(self, session_id: str, target_language: str = "en"):
        self.ws = await websockets.connect(f"{self.base_url}/ws/{session_id}")
        self.session_id = session_id
        self.target_language = target_language

    async def __call__(self, chunk: bytes) -> AsyncGenerator[Tuple[bool, bytes], None]:
        payload = {
            "type": "audio",
            "data": {
                "bytes": base64.b64encode(chunk).decode("utf-8"),
                "sample_rate": 16000,
                "final": False,
                # "src_lang": "en",
                "dst_lang": self.target_language,
            },
        }
        await self.ws.send(json.dumps(payload))

    async def results(self) -> AsyncGenerator[Tuple[bool, bytes], None]:
        async for message in self.ws:
            message = json.loads(message)
            if message["type"] == "asr":
                yield message["text"], None, None
            elif message["type"] == "ast":
                yield None, message["text"], None
            elif message["type"] == "audio":
                speech = message["bytes"]
                speech = base64.b64decode(speech.encode("utf-8"))
                sample_rate = message["sample_rate"]
                if self.resampler is None and sample_rate != 16000:
                    self.resampler = StreamingResampler(in_rate=sample_rate, out_rate=16000)
                speech = self.resampler(speech)
                yield None, None, speech
            else:
                raise ValueError(f"Unknown message type: {message['type']}")
