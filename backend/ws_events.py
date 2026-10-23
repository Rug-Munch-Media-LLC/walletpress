"""WebSocket event stream at /ws/events.

Clients subscribe to event types and receive pushes from the core event bus.
Tokens are read from the Sec-WebSocket-Protocol header or the first message —
never from the query string (query strings leak into access logs). The query
parameter remains as a deprecated fallback that logs a warning on use.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.event_bus import subscribe as subscribe_events

logger = logging.getLogger("wp")

router = APIRouter()

_ws_clients: dict[WebSocket, set[str]] = {}
_ws_rate: dict[WebSocket, float] = {}
_WS_RATE_LIMIT = 10  # messages per second per connection
_WS_AUTH_TIMEOUT = 5.0


@router.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    """Push wallet events to a subscribed client.

    Authentication order:
      1. Sec-WebSocket-Protocol: wp-auth-<API_KEY>  (not logged by proxies)
      2. First JSON message {"token": "<API_KEY>"} within 5s
      3. DEPRECATED ?token= query parameter (warns; to be removed)
    """
    await ws.accept()

    token = ""
    for protocol in ws.headers.get("sec-websocket-protocol", "").split(","):
        protocol = protocol.strip()
        if protocol.startswith("wp-auth-"):
            token = protocol[8:]
            break

    if not token:
        try:
            auth_msg = await asyncio.wait_for(ws.receive_json(), timeout=_WS_AUTH_TIMEOUT)
            token = auth_msg.get("token", "")
            if token and "subscribe" in auth_msg:
                subscriptions = auth_msg["subscribe"]
                if isinstance(subscriptions, list) and all(
                    isinstance(item, str) for item in subscriptions
                ):
                    _ws_clients[ws] = set(subscriptions)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception as e:
            logger.debug(f"WebSocket auth message error: {e}")

    if not token:
        query_token = ws.query_params.get("token", "")
        if query_token:
            logger.warning(
                "DEPRECATED: WebSocket ?token= query parameter used. "
                "This leaks tokens to access logs. Use Sec-WebSocket-Protocol header instead."
            )
            token = query_token

    if token:
        from core.auth import get_key_store

        if not get_key_store().verify(token):
            await ws.send_json({"error": "Invalid API key"})
            await ws.close()
            return

    _ws_clients.setdefault(ws, set())
    _ws_rate[ws] = time.monotonic()

    try:
        while True:
            data = await ws.receive_text()
            now = time.monotonic()
            if now - _ws_rate.get(ws, 0) < 1.0 / _WS_RATE_LIMIT:
                await ws.send_json(
                    {"event": "rate_limited", "data": {"message": "Slow down (max 10 msg/s)"}}
                )
                continue
            _ws_rate[ws] = now
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                if data == "ping":
                    await ws.send_json({"event": "pong"})
                continue
            if isinstance(msg, dict) and "subscribe" in msg:
                subscriptions = msg["subscribe"]
                if isinstance(subscriptions, list) and all(
                    isinstance(item, str) for item in subscriptions
                ):
                    _ws_clients[ws] = set(subscriptions)
                    await ws.send_json({"event": "subscribed", "data": {"events": subscriptions}})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.pop(ws, None)
        _ws_rate.pop(ws, None)


async def broadcast_ws(event_type: str, data: dict) -> None:
    """Broadcast an event to every client subscribed to it."""
    message = json.dumps({"event": event_type, "data": data})
    dead: list[WebSocket] = []
    for ws, subscriptions in list(_ws_clients.items()):
        if subscriptions and event_type not in subscriptions:
            continue
        try:
            await ws.send_text(message)
        except Exception as e:
            logger.debug(f"WebSocket send failed: {e}")
            dead.append(ws)
    for ws in dead:
        _ws_clients.pop(ws, None)
        _ws_rate.pop(ws, None)


def _forward_to_websocket(event_type: str, data: dict) -> None:
    """Event-bus callback: schedule a broadcast on the running loop."""
    asyncio.get_event_loop().create_task(broadcast_ws(event_type, data))


subscribe_events(_forward_to_websocket)
