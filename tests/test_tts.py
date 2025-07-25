import asyncio
import soundfile as sf
import numpy as np

from hyperpyyaml import load_hyperpyyaml

with open("luna_agent/conf/default.yaml", "r") as f:
    config = load_hyperpyyaml(f)


async def dummy_generator():
    text = "This is a test text for TTS." * 5

    def iterator():
        for i in range(0, len(text), 10):
            yield text[i : i + 3]

    return iterator()


async def test_tts():
    audio, sr = sf.read("./test/test.wav")
    audio = (audio * 32768.0).astype(np.int16).tobytes()
    tts = config.tts
    text_iterator = await dummy_generator()
    transcript = await tts(text_iterator)
    print(f"transcript: {transcript}")


if __name__ == "__main__":
    asyncio.run(test_tts())
