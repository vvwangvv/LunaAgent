import os
import asyncio
import torch
import logging
import json
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from silero_vad import load_silero_vad
from silero_vad.utils_vad import VADIterator
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

VAD_POOL_SIZE = int(os.environ.get("VAD_POOL_SIZE", "10"))
MIN_SILENCE_DURATION_MS = int(os.environ.get("MIN_SILENCE_DURATION_MS", "300"))
SPEECH_PAD_MS = int(os.environ.get("SPEECH_PAD_MS", "200"))


class SileroVad:
    def __init__(self):
        model = load_silero_vad(onnx=True)
        self.vad_iterator = VADIterator(
            model,
            sampling_rate=16000,
            min_silence_duration_ms=int(MIN_SILENCE_DURATION_MS),
            speech_pad_ms=int(SPEECH_PAD_MS),
        )
        self.window_size_samples = 512
        self.buffer = b""

    async def __call__(self, samples: bytes):
        samples = torch.frombuffer(self.buffer + samples, dtype=torch.int16).float() / 32768.0
        for i in range(0, len(samples), self.window_size_samples):
            if i + self.window_size_samples > len(samples):
                leftover = (samples[i:].numpy() * 32768.0).astype(np.int16).tobytes()
                self.buffer = leftover
                break
            chunk = samples[i : i + self.window_size_samples]
            speech_dict = self.vad_iterator(chunk)
            if speech_dict:
                yield speech_dict

    def reset(self):
        self.vad_iterator.reset_states()


model_pool: asyncio.Queue[SileroVad] = asyncio.Queue()


@asynccontextmanager
async def lifespan(app: FastAPI):
    for _ in range(VAD_POOL_SIZE):
        model_pool.put_nowait(SileroVad())
    yield


app = FastAPI(lifespan=lifespan)


@app.websocket("/vad")
async def vad_ws(ws: WebSocket):
    await ws.accept()
    buffer = b""
    vad: SileroVad = await model_pool.get()
    try:
        while True:
            try:
                chunk = await ws.receive_bytes()
            except WebSocketDisconnect:
                break
            buffer += chunk
            results = vad(chunk)
            async for r in results:
                await ws.send_text(json.dumps(r))
            await ws.send_text(json.dumps({"current": (len(buffer) - len(vad.buffer)) // 2}))

    finally:
        vad.reset()
        await model_pool.put(vad)


# uvicorn vad:app --port 8000
