from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import User
from app.realtime import connection_manager

router = APIRouter(tags=["realtime"])
EVENTS_SUBPROTOCOL = "atm-events"
TOKEN_SUBPROTOCOL_PREFIX = "bearer."


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, session: Session = Depends(get_db)) -> None:
    offered_protocols = {
        protocol.strip()
        for protocol in websocket.headers.get("sec-websocket-protocol", "").split(",")
    }
    token = next(
        (
            protocol[len(TOKEN_SUBPROTOCOL_PREFIX):]
            for protocol in offered_protocols
            if protocol.startswith(TOKEN_SUBPROTOCOL_PREFIX)
        ),
        None,
    )
    if EVENTS_SUBPROTOCOL not in offered_protocols or not token:
        await websocket.close(code=1008)
        return

    try:
        user: User = get_current_user(token, session)
    except Exception:
        await websocket.close(code=1008)
        return
    if not has_permission(user.role.name, "dashboard:read"):
        await websocket.close(code=1008)
        return

    await connection_manager.connect(websocket, user.id, user.username, user.role.name)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"event_type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(websocket)