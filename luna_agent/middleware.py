from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional
import asyncio

app = FastAPI()

# Shared connections
connections = {
    "agent_audio": None,
    "agent_event": None,
    "user_audio": None,
    "user_event": None,
}

import json
import base64

async def forward(src_ws: WebSocket, dst_ws: WebSocket, label: str, stream_type: str):
    try:
        while True:
            if stream_type == "audio":
                # Receive JSON with base64-encoded audio
                msg = await src_ws.receive_text()
                try:
                    payload = json.loads(msg)
                    b64 = payload["data"]
                    audio_bytes = base64.b64decode(b64)
                    print(f"[{label}] Audio chunk: {len(audio_bytes)} bytes")
                    await dst_ws.send_bytes(audio_bytes)
                except (json.JSONDecodeError, KeyError, base64.binascii.Error) as e:
                    print(f"[{label}] Error decoding audio JSON: {e}")
            elif stream_type == "event":
                msg = await src_ws.receive_text()
                try:
                    event = json.loads(msg)
                    print(f"[{label}] Event: {json.dumps(event, indent=2)}")
                except json.JSONDecodeError:
                    print(f"[{label}] Malformed event: {msg}")
                await dst_ws.send_text(msg)
    except WebSocketDisconnect:
        print(f"[{label}] disconnected")
    except Exception as e:
        print(f"[{label}] error: {e}")


async def maybe_pair_and_stream(kind: str):
    # Wait until both sides are connected
    if kind.startswith("agent"):
        peer_kind = kind.replace("agent", "user")
    else:
        peer_kind = kind.replace("user", "agent")

    ws1 = connections[kind]
    ws2 = connections[peer_kind]

    stream_type = "audio" if "audio" in kind else "event"
    if ws1 and ws2:
        # Launch bidirectional forwarding
        print(f"Pairing: {kind} <-> {peer_kind}")
        await asyncio.gather(
            forward(ws1, ws2, f"{kind} -> {peer_kind}", stream_type),
            forward(ws2, ws1, f"{peer_kind} -> {kind}", stream_type)
        )

# Generic handler
async def websocket_handler(websocket: WebSocket, kind: str):
    await websocket.accept()
    connections[kind] = websocket
    print(f"{kind} connected")

    try:
        await maybe_pair_and_stream(kind)
    finally:
        connections[kind] = None
        await websocket.close()
        print(f"{kind} connection closed")

# Define routes
@app.websocket("/ws/agent/audio")
async def ws_agent_audio(websocket: WebSocket):
    await websocket_handler(websocket, "agent_audio")

@app.websocket("/ws/agent/event")
async def ws_agent_event(websocket: WebSocket):
    await websocket_handler(websocket, "agent_event")

@app.websocket("/ws/user/audio")
async def ws_user_audio(websocket: WebSocket):
    await websocket_handler(websocket, "user_audio")

@app.websocket("/ws/user/event")
async def ws_user_event(websocket: WebSocket):
    await websocket_handler(websocket, "user_event")

# uvicorn middleware:app --host 0.0.0.0 --port 27020