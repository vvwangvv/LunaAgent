import base64
import json
from typing import AsyncGenerator, Tuple

import websockets

from luna_agent.utils import StreamingResampler, logger


class Interpret:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session_id = None
        self.ws = None
        self.resampler = None
        self.target_language = None

    async def setup(
        self,
        session_id: str,
        target_language: str = "en",
        voice_clone=False,
        generate_speech=True,
        noise_reduction=False,
    ):
        self.ws = await websockets.connect(f"{self.base_url}/ws/{session_id}")
        self.session_id = session_id
        self.target_language = target_language
        self.voice_clone = voice_clone
        self.generate_speech = generate_speech
        self.noise_reduction = noise_reduction

    async def __call__(self, chunk: bytes) -> AsyncGenerator[Tuple[bool, bytes], None]:
        #
        payload = {
            "type": "audio",
            "data": {
                "bytes": base64.b64encode(chunk).decode("utf-8"),
                "sample_rate": 16000,
                "final": False,
                # "src_lang": "en",
                "tgt_lang": self.target_language,
                "voice_clone": self.voice_clone,
                "generate_speech": self.generate_speech,
                "noise_reduction": self.noise_reduction,
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
                    self.resampler = StreamingResampler(src_rate=sample_rate, dst_rate=16000)
                    speech = self.resampler(speech)
                yield None, None, speech
            else:
                raise ValueError(f"Unknown message type: {message['type']}")

    async def close(self):
        try:
            await self.ws.close()
        except Exception as e:
            logger.error(f"Error closing Interpret websocket: {e}")
