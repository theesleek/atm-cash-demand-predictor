from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectedClient:
    user_id: int
    username: str
    role: str


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[int, tuple[WebSocket, ConnectedClient]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def connected_users(self) -> tuple[ConnectedClient, ...]:
        return tuple(client for _websocket, client in self._clients.values())

    async def connect(self, websocket: WebSocket, user_id: int, username: str, role: str) -> None:
        self._loop = asyncio.get_running_loop()
        await websocket.accept(subprotocol="atm-events")
        self._clients[id(websocket)] = (websocket, ConnectedClient(user_id, username, role))

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.pop(id(websocket), None)

    async def broadcast(self, event: dict[str, Any]) -> None:
        for client_key, (websocket, _client) in tuple(self._clients.items()):
            try:
                await websocket.send_json(event)
            except Exception:
                self._clients.pop(client_key, None)

    def publish(self, event: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def schedule_broadcast() -> None:
            task = loop.create_task(self.broadcast(event))
            task.add_done_callback(self._consume_task_error)

        try:
            loop.call_soon_threadsafe(schedule_broadcast)
        except RuntimeError:
            return

    @staticmethod
    def _consume_task_error(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("WebSocket broadcast task failed")


connection_manager = ConnectionManager()


def publish_realtime_event(
    event_type: str,
    entity_type: str,
    entity_id: str | int,
    *,
    atm_id: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    source: str,
) -> None:
    event: dict[str, Any] = {
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "atm_id": atm_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "severity": severity,
        "source": source,
    }
    connection_manager.publish(event)