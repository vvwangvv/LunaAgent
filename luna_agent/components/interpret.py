import base64
import websockets
import json
from typing import AsyncGenerator, Tuple


class Interpret:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session_id = None

    async def setup(self, session_id: str):
        self.ws = await websockets.connect(self.base_url)
        self.session_id = session_id

    async def __call__(self, chunk: bytes) -> AsyncGenerator[Tuple[bool, bytes], None]:
        self.data += chunk
        await self.ws.send(chunk)

    async def results(self) -> AsyncGenerator[Tuple[bool, bytes], None]:
        async for message in self.ws:
            message = json.loads(message)
            asr_text = ast_text = speech = None
            asr_text = message.get("asr", asr_text)
            ast_text = message.get("ast", ast_text)
            speech = message.get("speech", speech)
            if speech:
                speech = base64.b64decode(speech.encode("utf-8"))
            yield (asr_text, ast_text, speech)
