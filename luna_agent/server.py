import logging
import argparse
from luna_agent.utils import safe_create_task
from hyperpyyaml import load_hyperpyyaml
from fastapi import FastAPI, Request
import uvicorn
from luna_agent.agent import LunaAgent

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("luna_agent")
logger.setLevel(logging.INFO)

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=str, help="Path to the config file", default="conf/config.yaml")
parser.add_argument("--port", type=int, default=8000)
args, _ = parser.parse_known_args()

app = FastAPI()


@app.post("/start_session")
async def start_session(request: Request):
    body = await request.json()
    sample_rate = body.get("sample_rate", 16000)
    config = load_hyperpyyaml(args.config)
    session = await LunaAgent.create(config, user_audio_sample_rate=sample_rate)
    safe_create_task(session.listen())
    logger.info(f"Started session with id: {session.session_id}")
    return {"session_id": session.session_id}

@app.post("/mute")
async def mute(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    LunaAgent.sessions.get(session_id).user_mute_self()
    return {"status": "success"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=args.port)
