import asyncio
import os

import httpx
import uvicorn
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["*"] for all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared connections
connections = {
    "agent_audio": {},
    "agent_event": {},
    "user_audio": {},
    "user_event": {},
}


AGENT_PORT = int(os.getenv("AGENT_PORT", "9002"))

import base64
import json


async def forward(src_ws: WebSocket, dst_ws: WebSocket, label: str):
    try:
        while True:
            if label == "agent_audio -> user_audio":
                # Receive JSON with base64-encoded audio
                msg = await src_ws.recv()
                try:
                    payload = json.loads(msg)
                    if payload.get("data_type") != "bytes":
                        continue
                    b64 = payload["data"]
                    audio_bytes = base64.b64decode(b64)
                    print(f"[{label}] Audio chunk: {len(audio_bytes)} bytes")
                    await dst_ws.send_bytes(audio_bytes)
                except (json.JSONDecodeError, KeyError, base64.binascii.Error) as e:
                    print(f"[{label}] Error decoding audio JSON: {e}")
            elif label == "agent_event -> user_event" or label == "user_event -> agent_event":
                if label == "agent_event -> user_event":
                    msg = await src_ws.recv()
                else:
                    msg = await src_ws.receive_text()
                try:
                    event = json.loads(msg)
                    print(f"[{label}] Event: {json.dumps(event, indent=2)}")
                except json.JSONDecodeError:
                    print(f"[{label}] Malformed event: {msg}")
                await dst_ws.send_text(msg)
            else:
                assert label == "user_audio -> agent_audio"
                audio_bytes = await src_ws.receive_bytes()
                print(f"[{label}] Audio chunk: {len(audio_bytes)} bytes")
                await dst_ws.send(audio_bytes)
    except WebSocketDisconnect:
        print(f"[{label}] disconnected")
        await asyncio.gather(dst_ws.close(), src_ws.close())
    except Exception as e:
        print(f"[{label}] error: {e}")
        raise


async def pair_and_stream(kind: str, session_id: str):
    if kind.startswith("agent"):
        peer_kind = kind.replace("agent", "user")
    else:
        peer_kind = kind.replace("user", "agent")

    ws1 = connections[kind][session_id]

    # Wait until both sides are connected
    # FIXME: add timeout
    while session_id not in connections[peer_kind]:
        print(f"[{session_id}] waiting for peer connection...")
        await asyncio.sleep(1)
    ws2 = connections[peer_kind][session_id]

    if ws1 and ws2:
        # Launch bidirectional forwarding
        print(f"Forwarding: {kind} -> {peer_kind}")
        await asyncio.gather(
            forward(ws1, ws2, f"{kind} -> {peer_kind}"),
            forward(ws2, ws1, f"{peer_kind} -> {kind}"),
        )


# Generic handler
async def websocket_handler(websocket: WebSocket, kind: str, session_id: str):
    await websocket.accept()
    connections[kind][session_id] = websocket
    print(f"{kind} connected")
    try:
        await pair_and_stream(kind, session_id)
    finally:
        connections[kind].pop(session_id, None)
        await websocket.close()
        print(f"{kind} connection closed")


@app.websocket("/ws/user/audio/{session_id}")
async def ws_user_audio(websocket: WebSocket, session_id: str):
    await websocket_handler(websocket, "user_audio", session_id)


@app.websocket("/ws/user/event/{session_id}")
async def ws_user_event(websocket: WebSocket, session_id: str):
    await websocket_handler(websocket, "user_event", session_id)


@app.post("/start_session")
async def start_session(request: Request):
    print(f"Forwarding to: {AGENT_PORT}")
    async with httpx.AsyncClient() as client:
        response = await client.post(f"http://localhost:{AGENT_PORT}/start_session", json=await request.json())

    session_id = response.json().get("session_id")
    connections["agent_audio"][session_id] = await websockets.connect(
        f"ws://localhost:{AGENT_PORT}/ws/agent/audio/{session_id}"
    )
    connections["agent_event"][session_id] = await websockets.connect(
        f"ws://localhost:{AGENT_PORT}/ws/agent/event/{session_id}"
    )
    print(f"Session started with ID: {session_id}")
    return Response(content=response.content, media_type=response.headers.get("Content-Type", "application/json"))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    PORT = int(os.getenv("MIDDLEWARE_PORT", "28002"))
    args = parser.parse_args()
    uvicorn.run("middleware:app", host="0.0.0.0", port=PORT, reload=True)
