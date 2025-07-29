import asyncio
import soundfile as sf
import numpy as np
from luna_agent.utils import pcm2wav

from hyperpyyaml import load_hyperpyyaml

with open("config/default.yaml", "r") as f:
    config = load_hyperpyyaml(f)

audio, sr = sf.read("./tests/test.wav")
audio = (audio * 32768.0).astype(np.int16).tobytes()

def test_asr():
    async def fun():
        asr = config["asr"]
        transcript = await asr(pcm2wav(audio))
        print(f"transcript: {transcript}")
    asyncio.run(fun())


def test_vad():
    async def fun():
        vad = config["vad"]
        await vad.setup()
        async def detect_speech():
            for i in range(0, len(audio), 2048):
                chunk = audio[i : i + 2048]
                await vad(chunk)
            await asyncio.sleep(.5)
            await vad.ws.close()

        async def collect_vad_results():
            async for user_is_speaking, user_speech in vad.results():
                if user_speech:
                    print(f"user_speech: {len(user_speech)}")
        await asyncio.gather(detect_speech(), collect_vad_results())
    asyncio.run(fun())

def test_tts():
    control_params = {
        "speech": audio,
    }
    async def dummy_generator():
        text = "今天天气真不错，适合出去玩。" * 2
        async def iterator():
            for i in range(0, len(text), 3):
                yield text[i : i + 3]
        return iterator()

    async def fun():
        tts = config["tts"]
        slm_task = asyncio.create_task(dummy_generator())
        text_iterator = await slm_task

        tts_task = asyncio.create_task(tts(text_iterator, control_params=control_params))
        speech_iterator = await tts_task
        speech = b""
        async for chunk in speech_iterator:
            speech += chunk
        with open("./tests/output.wav", "wb") as f:
            f.write(pcm2wav(speech, 16000))
        
    asyncio.run(fun())

def test_tts_control():
    async def fun():
        text = "please reply with the voice of nezha"
        tts_control = config["tts_control"]
        control = await tts_control(text)
        assert control["timbre"] == "nezha"
    asyncio.run(fun())

def test_diar_control():
    async def fun():
        text = "how many speakers are there in this audio?"
        diar_control = config["diar_control"]
        control = await diar_control(text)
        assert control["diarization"] 
    asyncio.run(fun())

def test_diar():
    async def fun():
        text = "how many speakers are there in this audio?"
        diar = config["diar"]
        control = await diar(text)
        assert control["diarization"] 
    asyncio.run(fun())

# def test_slm():
#     async def fun():
#         slm = config["slm"]
#         transcript = await slm(pcm2wav(audio))
#         print(f"transcript: {transcript}")
#     asyncio.run(fun())