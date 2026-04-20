"""WebSocket route with live mode TTL management."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)

# Active WebSocket clients with their live mode TTL
_clients: dict[WebSocket, float] = {}  # ws -> ttl_expiry
_lock = asyncio.Lock()

DEFAULT_INTERVAL = 60
LIVE_INTERVAL = 10
LIVE_TTL = 30


async def get_active_poll_interval() -> int:
    """Return current poll interval based on active live mode clients."""
    now = time.time()
    async with _lock:
        # Clean expired TTLs
        expired = [
            ws
            for ws, expiry in _clients.items()
            if expiry > 0 and expiry < now
        ]
        for ws in expired:
            _clients[ws] = 0  # Reset to no live mode

        # Check if any client has active live mode
        has_live = any(
            expiry > now
            for expiry in _clients.values()
            if expiry > 0
        )
    return LIVE_INTERVAL if has_live else DEFAULT_INTERVAL


async def broadcast(message: dict) -> None:
    """Send a message to all connected WebSocket clients."""
    data = json.dumps(message)
    disconnected = []
    async with _lock:
        for ws in _clients:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            del _clients[ws]


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket connection handler."""
    await websocket.accept()
    async with _lock:
        _clients[websocket] = 0  # No live mode initially

    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "set_live_mode":
                enabled = msg.get("data", {}).get(
                    "enabled", False
                )
                async with _lock:
                    if enabled:
                        _clients[websocket] = (
                            time.time() + LIVE_TTL
                        )
                    else:
                        _clients[websocket] = 0

                # Notify about interval change
                interval = await get_active_poll_interval()
                await broadcast(
                    {
                        "type": "poll_interval",
                        "data": {
                            "interval_seconds": interval
                        },
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        async with _lock:
            _clients.pop(websocket, None)
