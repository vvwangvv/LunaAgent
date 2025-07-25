import asyncio
import soundfile as sf
import numpy as np
from luna_agent.utils import pcm2wav

from hyperpyyaml import load_hyperpyyaml

with open("luna_agent/conf/default.yaml", "r") as f:
    config = load_hyperpyyaml(f)


async def test_asr():
    audio, sr = sf.read("./test/test.wav")
    audio = (audio * 32768.0).astype(np.int16).tobytes()
    asr = config.asr
    transcript = await asr(pcm2wav(audio))
    print(f"transcript: {transcript}")


if __name__ == "__main__":
    asyncio.run(test_asr())
