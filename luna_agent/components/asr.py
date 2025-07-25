import httpx
from luna_agent.utils import pcm2wav


class ASR:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def __call__(self, audio: bytes) -> str:
        audio_wav = pcm2wav(audio)
        files = {"audio": ("test.wav", audio_wav, "application/octet-stream")}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(self.base_url, files=files)
        response.raise_for_status()
        transcript = response.json()["transcript"]
        return transcript
