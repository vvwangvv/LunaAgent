import asyncio
from asyncstdlib.itertools import tee
import soundfile as sf
import numpy as np
from luna_agent.utils import pcm2wav, safe_create_task

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
    control = {
        "speech": audio,
    }
    async def dummy_generator():
        text = "今天天气真不错，适合出去玩。" * 2
        async def generator():
            for i in range(0, len(text), 3):
                yield text[i : i + 3]
        return generator()

    async def fun():
        tts = config["tts"]
        text_generator = await safe_create_task(dummy_generator())

        speech_generator = await safe_create_task(tts(text_generator, control=control))
        speech = b""
        async for chunk in speech_generator:
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
        diar = config["diar"]
        await diar.setup(session_id="debug")
        result = await diar(audio)
    asyncio.run(fun())

def test_slm():
    async def fun():
        slm = config["slm"]
        await slm.setup(session_id="debug")
        history = []
        text_generator = await safe_create_task(slm(history, audio))
        t1, t2 = tee(text_generator, 2)  # Ensure the iterator can be reused
        i = 0
        async for chunk in t1:
            i += 1
            if i >= 3:
                await text_generator.aclose()
                break
            print(chunk, end="")
        response = ''.join([chunk async for chunk in t2])
        print(response)
    asyncio.run(fun())


# def test_interpret():
#     async def fun():
#         interpret = config["interpret"]
#         await interpret.setup(session_id="debug1")
#         async def do_interpret():
#             for i in range(0, len(audio), 2048):
#                 chunk = audio[i : i + 2048]
#                 await interpret(chunk)
#             await asyncio.sleep(10)
#             await interpret.ws.close()

#         async def collect_interpret_results():
#             all_speech = b""
#             async for asr_text, ast_text, speech in interpret.results():
#                 if asr_text:
#                     print(f"asr_text: {asr_text}")
#                 if ast_text:
#                     print(f"ast_text: {ast_text}")
#                 if speech:
#                     all_speech += speech
#                 with open("./tests/output.wav", "wb") as f:
#                     f.write(pcm2wav(speech, 16000))
#         await asyncio.gather(do_interpret(), collect_interpret_results())
#     asyncio.run(fun())