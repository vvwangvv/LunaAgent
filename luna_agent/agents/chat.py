import argparse
import time
import asyncio
import logging
import uvicorn
from uuid import uuid4
from typing import Optional
from typing import Dict, List
from asyncstdlib.itertools import tee
from hyperpyyaml import load_hyperpyyaml
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from luna_agent.utils import safe_create_task
from luna_agent.components import ASR, LLM, SLM, TTS, WebRTCEvent, WebRTCData, VAD
from luna_agent.components.slm import add_user_message, add_agent_message

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("luna_agent")
logger.setLevel(logging.INFO)


class LunaAgent:
    sessions = {}

    def __init__(self, config):
        self.vad: VAD = config["vad"]
        self.asr: ASR = config["asr"]
        self.slm: SLM = config["slm"]
        self.tts: TTS = config["tts"]
        self.data: WebRTCData = config["data"]
        self.event: WebRTCEvent = config["event"]
        self.tts_control: Optional[LLM] = config["tts_control"]
        self.diar_control: Optional[LLM] = config["diar_control"]

        self.session_id = uuid4().hex
        self.sample_rate = 16000

        self.history: List[Dict] = []
        self.user_is_speaking = False
        self.buffer = b""

    @classmethod
    async def create(cls, config, user_audio_sample_rate: int = 16000, user_audio_num_channels: int = 1):
        session = cls(config)
        await asyncio.gather(
            session.vad.setup(),
            session.slm.setup(session_id=session.session_id),
            session.data.setup(
                user_audio_sample_rate=user_audio_sample_rate, user_audio_num_channels=user_audio_num_channels
            ),
        )
        cls.sessions[session.session_id] = session
        return session

    async def listen(self):

        async def receive_user_audio():
            while not self.data.ready:
                await asyncio.sleep(0.1)
            async for chunk in self.data.read():
                self.buffer += chunk

        async def detect_speech():
            while True:
                if len(self.buffer) == 0:
                    await asyncio.sleep(0)
                    continue
                buffer, self.buffer = self.buffer, b""
                await self.vad(buffer)

        async def response_if_speech():
            prev_response_task = None
            async for user_is_speaking, user_speech in self.vad.results():
                if user_is_speaking != self.user_is_speaking:
                    self.user_is_speaking = user_is_speaking
                    await self.event.set_agent_can_speak(agent_can_speak=not user_is_speaking)
                if user_speech:
                    if prev_response_task and not prev_response_task.done():
                        prev_response_task.cancel()
                    prev_response_task = safe_create_task(self.response(user_speech))

        await asyncio.gather(receive_user_audio(), detect_speech(), response_if_speech())

    def mute_user(self):
        self.buffer += b"0x00" * self.sample_rate

    async def response(self, user_speech: bytes):
        print("In response")
        response_timestamp = int(time.time() * 1000)
        asr_task = safe_create_task(self.asr(user_speech))
        slm_task = safe_create_task(self.slm(history=self.history[:], audio=user_speech))
        user_transcript = await asr_task
        add_user_message(self.history, audio=user_speech, transcript=user_transcript)

        tts_control_task = safe_create_task(
            self.tts_control(user_transcript) if self.tts_control else asyncio.sleep(0, result={})
        )
        diar_control_task = safe_create_task(
            self.diar_control(user_transcript) if self.diar_control else asyncio.sleep(0, result={})
        )
        tts_control, diar_control = await asyncio.gather(tts_control_task, diar_control_task)
        tts_control["speech"] = user_speech
        tts_control["transcript"] = user_transcript

        if self.user_is_speaking or not diar_control.get("response", True):
            return

        agent_text_generator = await slm_task
        agent_text_generator1, agent_text_generator2 = tee(agent_text_generator, 2)
        tts_task = safe_create_task(self.tts(text_generateor=agent_text_generator1, control=tts_control))
        await self.event.set_avatar(tts_control["timbre"])

        agent_speech_generator = await tts_task
        try:
            async for agent_speech in agent_speech_generator:
                if self.user_is_speaking:
                    break
                await self.data.write(agent_speech, timestamp=response_timestamp)
        except asyncio.CancelledError:
            logger.info(f"response {response_timestamp} cancelled")
        finally:
            await agent_text_generator.aclose()
            await agent_speech_generator.aclose()
            agent_text = "".join([chunk async for chunk in agent_text_generator2])
            add_agent_message(history=self.history, message=agent_text)


parser = argparse.ArgumentParser()
parser.add_argument("--config", type=str, help="Path to the config file", default="config/chat.yaml")
parser.add_argument("--port", type=int, default=9002)
parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
args, _ = parser.parse_known_args()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["*"] for all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/start_session")
async def start_session(request: Request):
    body = await request.json()
    sample_rate = body.get("sample_rate", 16000)
    num_channels = body.get("num_channels", 1)
    with open(args.config, "r") as f:
        config = load_hyperpyyaml(f)
    session = await LunaAgent.create(
        config,
        user_audio_sample_rate=sample_rate,
        user_audio_num_channels=num_channels,
    )
    safe_create_task(session.listen())
    logger.info(f"Started session with id: {session.session_id}")
    return {"session_id": session.session_id}


@app.post("/mute")
async def mute(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    LunaAgent.sessions.get(session_id).mute_user()
    return {"status": "success"}


@app.websocket("/ws/agent/audio/{session_id}")
async def ws_user_audio(websocket: WebSocket, session_id: str):
    await websocket.accept()
    LunaAgent.sessions[session_id].data.ws = websocket
    await LunaAgent.sessions[session_id].data.disconnect.wait()


@app.websocket("/ws/agent/event/{session_id}")
async def ws_user_event(websocket: WebSocket, session_id: str):
    await websocket.accept()
    LunaAgent.sessions[session_id].event.ws = websocket
    await LunaAgent.sessions[session_id].event.disconnect.wait()


if __name__ == "__main__":
    uvicorn.run("chat:app", host="0.0.0.0", port=args.port, reload=args.reload)
