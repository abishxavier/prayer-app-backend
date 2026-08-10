from typing import Dict, List, Set, Tuple
from fastapi import WebSocket
import asyncio


class ConnectionManager:
    """
    Tracks active WebSocket connections per chat room, and a global
    set of currently-online user_ids across all rooms.
    """

    def __init__(self):
        # chat_id -> list of (user_id, WebSocket)
        self.active_connections: Dict[str, List[Tuple[str, WebSocket]]] = {}
        # user_id -> count of active connections (a user can have >1 socket open,
        # e.g. two chats or two devices, so we count rather than just add/remove)
        self.online_users: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self, chat_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.setdefault(chat_id, []).append((user_id, websocket))
            self.online_users[user_id] = self.online_users.get(user_id, 0) + 1

    async def disconnect(self, chat_id: str, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self.active_connections.get(chat_id, [])
            self.active_connections[chat_id] = [
                (uid, ws) for (uid, ws) in connections if ws is not websocket
            ]
            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]

            if user_id in self.online_users:
                self.online_users[user_id] -= 1
                if self.online_users[user_id] <= 0:
                    del self.online_users[user_id]

    async def broadcast(self, chat_id: str, message: dict, exclude_websocket: WebSocket | None = None) -> None:
        connections = self.active_connections.get(chat_id, [])
        # Snapshot before iterating since disconnects can mutate the list mid-broadcast
        stale: List[Tuple[str, WebSocket]] = []
        for user_id, ws in list(connections):
            if ws is exclude_websocket:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                # Connection is dead but hasn't been cleaned up yet — mark for removal
                stale.append((user_id, ws))

        if stale:
            async with self._lock:
                remaining = self.active_connections.get(chat_id, [])
                self.active_connections[chat_id] = [
                    (uid, ws) for (uid, ws) in remaining if (uid, ws) not in stale
                ]

    def is_online(self, user_id: str) -> bool:
        return self.online_users.get(user_id, 0) > 0

    def online_members_in_chat(self, chat_id: str) -> Set[str]:
        """Returns the set of user_ids currently connected to this specific chat room."""
        return {uid for uid, _ in self.active_connections.get(chat_id, [])}


# Single shared instance used across the app (imported by the ws endpoint and any
# REST routes that need to read presence, e.g. GET /chats/{chat_id}/online-members)
manager = ConnectionManager()