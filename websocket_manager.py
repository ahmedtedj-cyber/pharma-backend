"""
Gestionnaire WebSocket pour le broadcast en temps réel.
- ws://host/ws/camera/{session_id}  → flux frames annotées
- ws://host/ws/alerts               → alertes en temps réel
"""

import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gère toutes les connexions WebSocket actives."""

    def __init__(self):
        # camera_connections : session_id → set of websockets
        self.camera_connections: Dict[int, Set[WebSocket]] = {}
        # alert_connections : set of websockets
        self.alert_connections: Set[WebSocket] = set()

    # ── Connexions caméra ─────────────────────────────────────────────────

    async def connect_camera(self, websocket: WebSocket, session_id: int):
        await websocket.accept()
        if session_id not in self.camera_connections:
            self.camera_connections[session_id] = set()
        self.camera_connections[session_id].add(websocket)
        logger.info(f"WS caméra connecté — session {session_id} ({len(self.camera_connections[session_id])} clients)")

    def disconnect_camera(self, websocket: WebSocket, session_id: int):
        if session_id in self.camera_connections:
            self.camera_connections[session_id].discard(websocket)
            if not self.camera_connections[session_id]:
                del self.camera_connections[session_id]
        logger.info(f"WS caméra déconnecté — session {session_id}")

    async def broadcast_camera(self, session_id: int, data: dict):
        """Diffuse un résultat d'inspection à tous les clients de cette session."""
        if session_id not in self.camera_connections:
            return
        dead = set()
        for ws in self.camera_connections[session_id].copy():
            try:
                await ws.send_text(json.dumps(data, default=str))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.camera_connections[session_id].discard(ws)

    # ── Connexions alertes ────────────────────────────────────────────────

    async def connect_alerts(self, websocket: WebSocket):
        await websocket.accept()
        self.alert_connections.add(websocket)
        logger.info(f"WS alertes connecté ({len(self.alert_connections)} clients)")

    def disconnect_alerts(self, websocket: WebSocket):
        self.alert_connections.discard(websocket)

    async def broadcast_alert(self, alert_data: dict):
        """Diffuse une alerte à tous les clients connectés au canal alertes."""
        dead = set()
        for ws in self.alert_connections.copy():
            try:
                await ws.send_text(json.dumps(alert_data, default=str))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.alert_connections.discard(ws)

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "camera_sessions": list(self.camera_connections.keys()),
            "camera_client_count": sum(len(v) for v in self.camera_connections.values()),
            "alert_client_count": len(self.alert_connections)
        }


manager = ConnectionManager()
