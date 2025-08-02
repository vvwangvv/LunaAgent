import httpx
from typing import AsyncGenerator
import json
import logging

from uuid import uuid4
from luna_agent.utils import pcm2wav
import re

logger = logging.getLogger("luna_agent")


def extract_tts_text(text):
    punctuation = r"[，。！？,.!?:：；;；、\n\t\r•]"
    for i in range(len(text), 10, -1):
        prefix = text[:i]
        if re.search(punctuation + r"$", prefix) and len(prefix) > 10:
            return prefix, text[i:]
    return "", text


class TTS:
    def __init__(self, base_url, force_default=False):
        self.base_url = base_url
        self.sample_rate = 16000
        self.force_default = force_default

    def setup(self):
        logger.info("StreamingTTSComponent setup")

    async def tts(self, text: str, control=None):
        control = {} if control is None else control.copy()
        text = text.strip()
        if not text:
            raise StopIteration("No text to synthesize")

        control["stream"] = True
        control["text_frontend"] = True
        control["gen_text"] = text
        control["session_id"] = control.pop("session_id", uuid4().hex)
        control["dtype"] = "np.int16"
        control["ref_text"] = control.pop("transcript", "")
        control["voice"] = control.pop("timbre", "default")
        ref_audio = control.pop("speech", None)

        files = {} if ref_audio is None else {"ref_audio": pcm2wav(ref_audio)}

        data = {"params": json.dumps(control)}

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(self.base_url, files=files, data=data)
            async for chunk in response.aiter_bytes(chunk_size=4096):
                if chunk:
                    logger.debug(f"Streaming TTS chunk sent {len(chunk)} bytes")
                    yield chunk

    async def __call__(self, text_generateor: AsyncGenerator[str, None] | str, control={}):
        control["response_id"] = str(uuid4())
        if self.force_default:
            control = {
                "voice": "default",
                "speed": "default",
                "emotion": "default",
            }

        async def generator():
            text = ""
            async for text_partial in text_generateor:
                text += text_partial
                tts_text, text = extract_tts_text(text)
                if tts_text:
                    async for chunk in self.tts(tts_text, control=control):
                        yield chunk
            if text:
                async for chunk in self.tts(text, control=control):
                    yield chunk

        return generator()
