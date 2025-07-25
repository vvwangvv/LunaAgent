import asyncio
import soundfile as sf
import numpy as np
from luna_agent.utils import pcm2wav

from hyperpyyaml import load_hyperpyyaml

with open("luna_agent/conf/default.yaml", "r") as f:
    config = load_hyperpyyaml(f)


async def test_tts_control():
    text = "please reply with the voice of nezha"
    tts_control = config.tts_control
    control = await tts_control(text)
    print(f"control: {control}")


if __name__ == "__main__":
    asyncio.run(test_tts_control())
