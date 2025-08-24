import argparse
import asyncio
import logging
import uvicorn
from uuid import uuid4
from hyperpyyaml import load_hyperpyyaml
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from luna_agent.utils import safe_create_task
from luna_agent.components import WebRTCEvent, WebRTCData, Echo

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
        self.echo: Echo = config["echo"]

        self.session_id = uuid4().hex
        self.sample_rate = 16000

        self.buffer = b""

    @classmethod
    async def create(cls, config, user_audio_sample_rate: int = 16000, user_audio_num_channels: int = 1, **kwargs):
        session = cls(config)
        await asyncio.gather(
            session.data.setup(read_src_sr=user_audio_sample_rate, read_src_channels=user_audio_num_channels),
            session.echo.setup(),
        )
        cls.sessions[session.session_id] = session
        return session

    async def listen(self):

        async def receive_user_audio():
            while not self.data.ready:
                await asyncio.sleep(0.1)
            async for chunk in self.data.read():
                self.buffer += chunk

        async def echo():
            while True:
                if len(self.buffer) == 0:
                    await asyncio.sleep(0)
                    continue
                buffer, self.buffer = self.buffer, b""
                await self.data.write(buffer)

        await asyncio.gather(receive_user_audio(), echo())


parser = argparse.ArgumentParser()
parser.add_argument("--config", type=str, help="Path to the config file", default="config/echo.yaml")
parser.add_argument("--port", type=int, default=9003)
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
    uvicorn.run("echo:app", host="0.0.0.0", port=args.port, reload=args.reload)
