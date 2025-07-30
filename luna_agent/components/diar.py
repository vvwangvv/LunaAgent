import json
import logging
import httpx
import hashlib
from luna_agent.utils import pcm2wav

logger = logging.getLogger("luna_agent")


class Diar:
    def __init__(self, base_url, min_speaker_num=1, max_speaker_num=2, speaker_num=None):
        self.sample_rate = 16000
        self.base_url = base_url
        self.min_speaker_num = min_speaker_num
        self.max_speaker_num = max_speaker_num
        self.speaker_num = speaker_num

    async def setup(self, session_id: str):
        self.session_id = session_id

    async def __call__(self, audio: bytes):
        params = {
            "session_id": self.session_id,
            "sent_id": hashlib.md5(audio).hexdigest(),
            "min_spk": self.min_speaker_num,
            "max_spk": self.max_speaker_num,
            "num_spk": self.speaker_num,
            "suffix": "wav",
        }
        files = {"new_audio": pcm2wav(audio, self.sample_rate)}
        data = {"params": json.dumps(params)}

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(self.base_url, files=files, data=data)
            response.raise_for_status()
            return response.json()
