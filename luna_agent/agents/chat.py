import argparse
import asyncio
import logging
import os
import time
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

import uvicorn
from asyncstdlib.itertools import tee
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from hyperpyyaml import load_hyperpyyaml

from luna_agent.components import (
    ASR,
    LLM,
    SLM,
    TTS,
    VAD,
    WebRTCDataLiveStream,
    WebRTCEvent,
)
from luna_agent.components.slm import add_agent_message, add_user_message
from luna_agent.utils import AsyncTaskMixin, logger, safe_create_task

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger.setLevel(logging.INFO)


class AgentStatus(Enum):
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class LunaAgent(AsyncTaskMixin):
    sessions = {}

    def __init__(self, config):
        super().__init__()
        self.vad: VAD = config["vad"]
        self.asr: ASR = config["asr"]
        self.slm: SLM = config["slm"]
        self.tts: TTS = config["tts"]
        self.data: WebRTCDataLiveStream = config["data"]
        self.event: WebRTCEvent = config["event"]
        self.tts_control: Optional[LLM] = config["tts_control"]
        self.diar_control: Optional[LLM] = config["diar_control"]

        self.session_id = uuid4().hex
        self.sample_rate = 16000

        self.history: List[Dict] = []
        self.agent_status = AgentStatus.LISTENING
        self.buffer = asyncio.Queue()
        self.prev_response_task: Optional[asyncio.Task] = None

    @classmethod
    async def create(cls, config, user_audio_sample_rate: int = 16000, user_audio_num_channels: int = 1):
        session = cls(config)
        await asyncio.gather(
            session.vad.setup(),
            session.slm.setup(session_id=session.session_id),
            session.tts.setup(session_id=session.session_id),
            session.data.setup(
                read_src_sr=user_audio_sample_rate,
                read_src_channels=user_audio_num_channels,
                write_src_sr=session.tts.sample_rate,
                write_dst_sr=session.tts.sample_rate,
            ),
        )
        cls.sessions[session.session_id] = session

        async def on_flush():
            await session.agent_status_changed(AgentStatus.LISTENING)

        session.data.on_flush = on_flush
        return session

    async def listen(self):

        async def receive_user_audio():
            while not self.data.ready:
                await asyncio.sleep(0.1)
            try:
                async for chunk in self.data.read():
                    logger.debug(f"Received audio chunk of size {len(chunk)}")
                    await self.buffer.put(chunk)
                await self.buffer.put(None)
            except WebSocketDisconnect:
                await self.destroy()

        async def detect_speech():
            while True:
                chunk = await self.buffer.get()
                if chunk is None:
                    break
                await self.vad(chunk)

        async def response_if_speech():
            async for user_is_speaking, user_speech in self.vad.results():
                if self.agent_status != AgentStatus.LISTENING and user_is_speaking:
                    logger.info(f"User interrupt: {user_is_speaking}")
                    await self.agent_status_changed(AgentStatus.LISTENING)
                    await self.cancel_prev_response()
                if user_speech is not None:
                    await self.cancel_prev_response()
                    self.prev_response_task = self.create_task(self.response(user_speech))

        await asyncio.gather(
            receive_user_audio(), self.create_task(detect_speech()), self.create_task(response_if_speech())
        )

    async def mute_user(self):
        logger.info("User muted")
        chunk = b"0x00" * self.sample_rate
        await self.buffer.put(chunk)

    async def response(self, user_speech: bytes):
        await self.agent_status_changed(AgentStatus.THINKING)
        response_timestamp = int(time.time() * 1000)
        asr_task = self.create_task(self.asr(user_speech))
        slm_task = self.create_task(self.slm(history=self.history[:], audio=user_speech))
        user_transcript = await asr_task
        logger.info(f"User transcript: {user_transcript}")
        add_user_message(self.history, audio=user_speech, transcript=user_transcript)

        tts_control_task = self.create_task(
            self.tts_control(user_transcript) if self.tts_control else asyncio.sleep(0, result={})
        )
        diar_control_task = self.create_task(
            self.diar_control(user_transcript) if self.diar_control else asyncio.sleep(0, result={})
        )
        tts_control, diar_control = await asyncio.gather(tts_control_task, diar_control_task)
        tts_control["speech"] = user_speech
        tts_control["transcript"] = user_transcript

        if not diar_control.get("response", True):
            return

        agent_text_generator = await slm_task
        agent_text_generator1, agent_text_generator2 = tee(agent_text_generator, 2)
        tts_task = self.create_task(self.tts(text_generateor=agent_text_generator1, control=tts_control))
        await self.set_avatar(tts_control["timbre"])

        agent_speech_generator = await tts_task
        await self.agent_status_changed(AgentStatus.SPEAKING)
        try:
            async for agent_speech in agent_speech_generator:
                logger.debug(f"Agent speech chunk of size {len(agent_speech)}")
                await self.data.write(agent_speech, timestamp=response_timestamp)
        except asyncio.CancelledError:
            logger.info(f"response {response_timestamp} cancelled")
        finally:
            await agent_text_generator.aclose()
            await agent_speech_generator.aclose()
            agent_text = "".join([chunk async for chunk in agent_text_generator2])
            add_agent_message(history=self.history, message=agent_text)
            self.data.flush()

    async def agent_status_changed(self, status: AgentStatus):
        self.agent_status = status
        await self.event.send_event(
            event="agent_status_changed",
            data={"timestamp": int(time.time() * 1000), "status": status.value},
        )

    async def set_avatar(self, avatar: str):
        if avatar != "default":
            await self.event.send_event(event="set_avatar", data={"avatar": avatar})

    async def cancel_prev_response(self):
        if self.prev_response_task and not self.prev_response_task.done():
            self.prev_response_task.cancel()
        self.data.clear()

    async def destroy(self):
        logger.info(f"Destroying session {self.session_id}")
        await asyncio.gather(
            self.cancel_prev_response(),
            self.vad.close(),
            self.data.close(),
            self.event.close(),
        )
        super().destroy()
        if self.session_id in self.sessions:
            del self.sessions[self.session_id]


PORT = int(os.getenv("AGENT_PORT", "28001"))
parser = argparse.ArgumentParser()
parser.add_argument("--config", type=str, help="Path to the config file", default="config/chat.yaml")
parser.add_argument("--port", type=int, default=PORT)
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
    await LunaAgent.sessions.get(session_id).mute_user()
    return {"status": "success"}


@app.websocket("/ws/agent/audio/{session_id}")
async def ws_user_audio(websocket: WebSocket, session_id: str):
    await LunaAgent.sessions[session_id].data.connect(websocket)
    await LunaAgent.sessions[session_id].data.closed.wait()


@app.websocket("/ws/agent/event/{session_id}")
async def ws_user_event(websocket: WebSocket, session_id: str):
    await LunaAgent.sessions[session_id].event.connect(websocket)
    await LunaAgent.sessions[session_id].event.closed.wait()


if __name__ == "__main__":
    uvicorn.run("chat:app", host="0.0.0.0", port=args.port, reload=args.reload)
