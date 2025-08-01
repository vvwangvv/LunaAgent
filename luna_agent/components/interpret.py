import base64
import websockets
import json
from typing import AsyncGenerator, Tuple


class Interpret:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session_id = None
        self.ws = None

    async def setup(self, session_id: str):
        self.ws = await websockets.connect(f"{self.base_url}/ws/{session_id}")
        self.session_id = session_id

    async def __call__(self, chunk: bytes) -> AsyncGenerator[Tuple[bool, bytes], None]:
        payload = {
            "type": "audio",
            "data": {
                "bytes": base64.b64encode(chunk).decode("utf-8"),
                "sample_rate": 16000,
                "final": False,
                "src_lang": "en",
                "dst_lang": "zh",
            }
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
                yield None, None, speech
            else:
                raise ValueError(f"Unknown message type: {message['type']}")