import json
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # room_name -> set of active WebSockets
        self.active_rooms: Dict[str, Set[WebSocket]] = {}
        # websocket -> metadata dict
        self.connection_meta: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, room_name: str, meta: dict):
        await websocket.accept()
        if room_name not in self.active_rooms:
            self.active_rooms[room_name] = set()
        self.active_rooms[room_name].add(websocket)
        self.connection_meta[websocket] = meta

    def disconnect(self, websocket: WebSocket, room_name: str):
        if room_name in self.active_rooms:
            self.active_rooms[room_name].discard(websocket)
            if not self.active_rooms[room_name]:
                del self.active_rooms[room_name]
        meta = self.connection_meta.pop(websocket, None)
        return meta

    async def broadcast(self, room_name: str, message: dict, exclude: WebSocket = None):
        if room_name not in self.active_rooms:
            return
        payload = json.dumps(message)
        dead_connections = []
        for connection in self.active_rooms[room_name]:
            if connection != exclude:
                try:
                    await connection.send_text(payload)
                except Exception:
                    dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead, room_name)

    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            pass


manager = ConnectionManager()


@router.websocket("/ws/meetings/{room_name}")
async def meeting_websocket_endpoint(websocket: WebSocket, room_name: str):
    # Query parameters can provide user identity
    query_params = dict(websocket.query_params)
    user_id = query_params.get("user_id", "")
    name = query_params.get("name", "Participant")
    uid = query_params.get("uid", "0")
    is_host = query_params.get("is_host", "false").lower() == "true"
    photo = query_params.get("photo", "")

    meta = {
        "room_name": room_name,
        "user_id": user_id,
        "name": name,
        "uid": uid,
        "is_host": is_host,
        "photo": photo,
        "joined_at": datetime.now(timezone.utc).isoformat(),
    }

    await manager.connect(websocket, room_name, meta)

    # Broadcast join event to all other peers in room
    await manager.broadcast(
        room_name,
        {
            "type": "participant:joined",
            "uid": uid,
            "user_id": user_id,
            "name": name,
            "photo": photo,
            "is_host": is_host,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        exclude=websocket,
    )

    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
            except Exception:
                continue

            event_type = msg.get("type", "")

            # Ensure sender info is attached
            if "name" not in msg:
                msg["name"] = name
            if "uid" not in msg:
                msg["uid"] = uid
            if "sender_id" not in msg:
                msg["sender_id"] = user_id
            if "timestamp" not in msg:
                msg["timestamp"] = datetime.now(timezone.utc).isoformat()

            # Handle different event types
            if event_type == "chat:message":
                # Broadcast chat message to everyone in room including sender confirmation
                await manager.broadcast(room_name, msg)
            elif event_type in [
                "participant:reaction",
                "participant:hand_raised",
                "participant:muted",
                "participant:camera_changed",
                "participant:removed",
                "host:settings_changed",
                "screen:start",
                "screen:stop",
                "meeting:ended",
                "waiting:request",
                "waiting:admit",
                "waiting:reject",
                "co_host:assigned",
                "participant:cohost",
            ]:
                # Broadcast real-time event to all peers in room
                await manager.broadcast(room_name, msg)
            else:
                # Default relay
                await manager.broadcast(room_name, msg, exclude=websocket)

    except WebSocketDisconnect:
        disconnected_meta = manager.disconnect(websocket, room_name)
        if disconnected_meta:
            await manager.broadcast(
                room_name,
                {
                    "type": "participant:left",
                    "uid": disconnected_meta.get("uid"),
                    "user_id": disconnected_meta.get("user_id"),
                    "name": disconnected_meta.get("name"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
    except Exception as e:
        manager.disconnect(websocket, room_name)
