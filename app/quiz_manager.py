# app/quiz_manager.py
import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket
import redis.asyncio as redis
import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
PUBSUB_CHANNEL_PREFIX = "quiz_channel:"

class QuizManager:
    """
    Minimal WebSocket connection manager + Redis pub/sub publisher.
    Each quiz has its own channel: quiz_channel:{quiz_id}
    """
    def __init__(self, redis_url: str = REDIS_URL):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.connections: Dict[str, Set[WebSocket]] = {}
        self._pubsub_task = None

    async def start_listener(self):
        if self._pubsub_task:
            return
        self._pubsub_task = asyncio.create_task(self._listen_pubsub())

    async def _listen_pubsub(self):
        ps = self.redis.pubsub()
        await ps.psubscribe(f"{PUBSUB_CHANNEL_PREFIX}*")
        async for message in ps.listen():
            if message is None:
                continue
            if message.get("type") in ("message", "pmessage"):
                channel = message.get("channel")
                data = message.get("data")
                # ensure data is string
                if isinstance(data, bytes):
                    data = data.decode()
                await self._broadcast_channel(channel, data)

    async def _broadcast_channel(self, channel: str, data: str):
        if not channel.startswith(PUBSUB_CHANNEL_PREFIX):
            return
        quiz_id = channel.split(":", 1)[1]
        conns = self.connections.get(quiz_id, set()).copy()
        disconnects = []
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                disconnects.append(ws)
        for d in disconnects:
            await self.disconnect(quiz_id, d)

    async def connect(self, quiz_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(quiz_id, set()).add(websocket)

    async def disconnect(self, quiz_id: str, websocket: WebSocket):
        conns = self.connections.get(quiz_id)
        if conns and websocket in conns:
            conns.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass

    async def publish_quiz(self, quiz_id: str, payload: dict):
        channel = f"{PUBSUB_CHANNEL_PREFIX}{quiz_id}"
        await self.redis.publish(channel, json.dumps(payload))
