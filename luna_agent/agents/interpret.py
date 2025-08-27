import argparse
import asyncio
import logging
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from hyperpyyaml import load_hyperpyyaml

from luna_agent.components import Interpret, WebRTCData, WebRTCEvent
from luna_agent.utils import safe_create_task

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("luna_agent")
logger.setLevel(logging.INFO)


class LunaAgent:
    sessions = {}

    def __init__(self, config):
        self.data: WebRTCData = config["data"]
        self.event: WebRTCEvent = config["event"]
        self.interpret: Interpret = config["interpret"]
        self.session_id = uuid4().hex
        self.sample_rate = 16000
        self.buffer = asyncio.Queue()

    @classmethod
    async def create(
        cls,
        config,
        user_audio_sample_rate: int = 16000,
        user_audio_num_channels: int = 1,
        target_language: str = "en",
        voice_clone=False,
        generate_speech=True,
        noise_reduction=True,
    ):
        session = cls(config)
        await asyncio.gather(
            session.data.setup(read_src_sr=user_audio_sample_rate, read_src_channels=user_audio_num_channels),
            session.interpret.setup(
                session_id=session.session_id,
                target_language=target_language,
                voice_clone=voice_clone,
                generate_speech=generate_speech,
                noise_reduction=noise_reduction,
            ),
        )
        cls.sessions[session.session_id] = session
        return session

    async def listen(self):

        async def receive_user_audio():
            while not self.data.ready:
                await asyncio.sleep(0.1)
            try:
                async for chunk in self.data.read():
                    await self.buffer.put(chunk)
                await self.buffer.put(None)
            except WebSocketDisconnect:
                await self.destroy()

        async def interpret_audio():
            while True:
                chunk = await self.buffer.get()
                if chunk is None:
                    break

                await self.interpret(chunk)

        async def response():
            async for asr_text, ast_text, speech in self.interpret.results():
                if asr_text is not None:
                    await self.data.write(asr_text, text_type="asr")
                if ast_text is not None:
                    await self.data.write(ast_text, text_type="ast")
                if speech is not None:
                    await self.data.write(speech)

        await asyncio.gather(receive_user_audio(), interpret_audio(), response())

    async def destroy(self):
        logger.info(f"Destroying session {self.session_id}")
        await asyncio.gather(
            self.data.close(),
            self.event.close(),
            self.interpret.close(),
        )
        if self.session_id in self.sessions:
            del self.sessions[self.session_id]


"""
Endpoints of Live Interpret Agent
"""

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=str, help="Path to the config file", default="config/interpret.yaml")
parser.add_argument("--port", type=int, default=9001)
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
    target_language = body.get("target_language", "en")
    voice_clone = body.get("voice_clone", False)
    generate_speech = body.get("generate_speech", True)
    noise_reduction = body.get("noise_reduction", True)
    print(body)
    with open(args.config, "r") as f:
        config = load_hyperpyyaml(f)
    session = await LunaAgent.create(
        config,
        user_audio_sample_rate=sample_rate,
        user_audio_num_channels=num_channels,
        target_language=target_language,
        voice_clone=voice_clone,
        generate_speech=generate_speech,
        noise_reduction=noise_reduction,
    )
    safe_create_task(session.listen())
    logger.info(f"Started session with id: {session.session_id}")
    return {"session_id": session.session_id}


@app.websocket("/ws/agent/audio/{session_id}")
async def ws_user_audio(websocket: WebSocket, session_id: str):
    await websocket.accept()
    LunaAgent.sessions[session_id].data.ws = websocket
    await LunaAgent.sessions[session_id].data.closed.wait()


@app.websocket("/ws/agent/event/{session_id}")
async def ws_user_event(websocket: WebSocket, session_id: str):
    await websocket.accept()
    LunaAgent.sessions[session_id].event.ws = websocket
    await LunaAgent.sessions[session_id].event.closed.wait()


if __name__ == "__main__":
    uvicorn.run("interpret:app", host="0.0.0.0", port=args.port, reload=args.reload)
