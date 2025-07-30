import logging
import argparse
from luna_agent.utils import safe_create_task
from hyperpyyaml import load_hyperpyyaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from luna_agent.agent import LunaAgent

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("luna_agent")
logger.setLevel(logging.INFO)

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=str, help="Path to the config file", default="config/default.yaml")
parser.add_argument("--port", type=int, default=8000)
args, _ = parser.parse_known_args()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000"],  # or ["*"] for all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/start_session")
async def start_session(request: Request):
    body = await request.json()
    sample_rate = body.get("sample_rate", 16000)
    with open(args.config, "r") as f:
        config = load_hyperpyyaml(f)
    session = await LunaAgent.create(config, user_audio_sample_rate=sample_rate)
    safe_create_task(session.listen())
    logger.info(f"Started session with id: {session.session_id}")
    return {"session_id": session.session_id}

@app.post("/mute")
async def mute(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    LunaAgent.sessions.get(session_id).mute_user()
    return {"status": "success"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=args.port)
