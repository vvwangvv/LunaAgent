import asyncio
import soundfile as sf
import numpy as np

from hyperpyyaml import load_hyperpyyaml

with open("luna_agent/conf/default.yaml", "r") as f:
    config = load_hyperpyyaml(f)


async def test_vad():
    audio, sr = sf.read("./test/test.wav")
    audio = (audio * 32768.0).astype(np.int16).tobytes()

    vad = config.vad
    await vad.setup()

    for i in range(0, len(audio), 2048):
        chunk = audio[i : i + 2048]
        async for user_is_speaking, user_speech in vad(chunk):
            print(f"user_is_speaking: {user_is_speaking}")
            if user_speech is not None:
                print(f"user_speech: {len(user_speech)}")
            else:
                print("user_speech: None")


if __name__ == "__main__":
    asyncio.run(test_vad())
