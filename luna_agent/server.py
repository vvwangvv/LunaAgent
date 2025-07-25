import logging
import argparse
import asyncio
from hyperpyyaml import load_hyperpyyaml
from fastapi import FastAPI
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


@app.get("/start_session")
async def start_session(sample_rate: int):
    config = load_hyperpyyaml(args.config)
    session = await LunaAgent.create(config, user_audio_sample_rate=sample_rate)
    asyncio.create_task(session.listen())
    logger.info(f"Started session with id: {session.session_id}")
    return {"session_id": session.session_id}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=args.port)
