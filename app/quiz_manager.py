# app/quiz_manager.py (Extended for Day 3 Logic with Correct Schemas)
import json
import asyncio
from typing import Dict, Set, List, Optional, Tuple
from fastapi import WebSocket
import redis.asyncio as redis
import os
import logging
from uuid import uuid4
from .schemas import Quiz, Question, AnswerSubmission # <-- FIX: Use relative import

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
PUBSUB_CHANNEL_PREFIX = "quiz_channel:"
QUIZ_STATE_PREFIX = "quiz_state:" 

class QuizManager:
    """Manages WebSocket connections, Redis Pub/Sub, and quiz state in Redis."""
    def __init__(self, redis_url: str = REDIS_URL):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.connections: Dict[str, Set[WebSocket]] = {}
        self._pubsub_task = None
        logger.info(f"QuizManager initialized with Redis URL: {redis_url}")

    # --- Connection & PubSub Methods ---
    async def start_listener(self):
        if self._pubsub_task and not self._pubsub_task.done():
            logger.info("PubSub listener already running.")
            return
        logger.info("Starting Redis PubSub listener...")
        self._pubsub_task = asyncio.create_task(self._listen_pubsub())
        self._pubsub_task.add_done_callback(self._handle_listener_completion)

    def _handle_listener_completion(self, task: asyncio.Task):
        try: task.result(); logger.info("PubSub listener task finished cleanly.")
        except asyncio.CancelledError: logger.info("PubSub listener task was cancelled.")
        except Exception: logger.exception("PubSub listener task failed unexpectedly!")

    async def _listen_pubsub(self):
        async with self.redis.pubsub() as ps:
            await ps.psubscribe(f"{PUBSUB_CHANNEL_PREFIX}*")
            logger.info(f"Subscribed to Redis channels pattern: {PUBSUB_CHANNEL_PREFIX}*")
            while True:
                try:
                    message = await ps.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message is None: await asyncio.sleep(0.01); continue
                    if message.get("type") == "pmessage":
                        channel = message.get("channel")
                        data = message.get("data")
                        if isinstance(data, bytes): data = data.decode()
                        await self._broadcast_channel(channel, data)
                except redis.ConnectionError: logger.error("Redis connection error. Retrying..."); await asyncio.sleep(5); await ps.psubscribe(f"{PUBSUB_CHANNEL_PREFIX}*")
                except Exception: logger.exception("Error in Redis listener loop."); await asyncio.sleep(1)

    async def _broadcast_channel(self, channel: str, data: str):
        if not channel.startswith(PUBSUB_CHANNEL_PREFIX): return
        try:
            quiz_id = channel.split(PUBSUB_CHANNEL_PREFIX, 1)[1].strip('<>')
            active_connections = self.connections.get(quiz_id, set()).copy()
            if not active_connections: return
            logger.info(f"Broadcasting to {len(active_connections)} connections for quiz_id: {quiz_id}")
            tasks = [self._send_to_websocket(ws, data, quiz_id) for ws in active_connections]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            disconnects = [ws for i, (ws, res) in enumerate(zip(active_connections, results)) if isinstance(res, Exception)]
            if disconnects: await asyncio.gather(*(self.disconnect(quiz_id, ws) for ws in disconnects))
        except IndexError: logger.error(f"Could not extract quiz_id cleanly from channel: {channel}")
        except Exception: logger.exception(f"Unexpected error during broadcast for channel: {channel}")

    async def _send_to_websocket(self, websocket: WebSocket, data: str, quiz_id: str):
        try: await websocket.send_text(data); logger.info(f"Sent data via WebSocket for quiz {quiz_id}")
        except Exception as e: raise e

    async def connect(self, quiz_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(quiz_id, set()).add(websocket)
        logger.info(f"Client connected to quiz_id: {quiz_id}. Total: {len(self.connections.get(quiz_id, set()))}")

    async def disconnect(self, quiz_id: str, websocket: WebSocket):
        conns = self.connections.get(quiz_id)
        if conns and websocket in conns: conns.remove(websocket)
        logger.info(f"Client disconnected from quiz_id: {quiz_id}. Remaining: {len(conns) if conns else 0}")
        if conns is not None and not conns: del self.connections[quiz_id]; logger.info(f"Removed empty connection set for quiz_id: {quiz_id}")
        try:
             if hasattr(websocket, 'client_state') and websocket.client_state.name == 'CONNECTED':
                 await websocket.close()
        except Exception: pass

    async def publish_message(self, quiz_id: str, message_type: str, data: dict):
        channel = f"{PUBSUB_CHANNEL_PREFIX}{quiz_id}"
        message = json.dumps({"type": message_type, **data})
        logger.info(f"Publishing message to Redis channel: {channel}")
        await self.redis.publish(channel, message)

    # --- Day 3 Methods ---
    async def store_quiz_state(self, quiz: Quiz):
        """Stores the initial Quiz object and player data structure in Redis."""
        quiz_id = quiz.quiz_id
        quiz_key = f"{QUIZ_STATE_PREFIX}{quiz_id}"
        quiz_data_to_store = {
            "id": quiz_id,
            "title": quiz.topic,
            "topic": quiz.topic,
            "difficulty": quiz.difficulty,
            "questions": [q.model_dump() for q in quiz.questions],
            "players": {}
        }
        await self.redis.set(quiz_key, json.dumps(quiz_data_to_store))
        logger.info(f"Stored initial quiz state {quiz_id} in Redis.")

    async def get_quiz_state(self, quiz_id: str) -> Optional[dict]:
        """Retrieves the full quiz state from Redis."""
        quiz_key = f"{QUIZ_STATE_PREFIX}{quiz_id}"
        data = await self.redis.get(quiz_key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse quiz state from Redis for quiz_id: {quiz_id}")
                return None
        logger.warning(f"Quiz state not found in Redis for quiz_id: {quiz_id}")
        return None

    async def join_quiz(self, quiz_id: str, player_name: str) -> Optional[dict]:
        """Adds a player to the quiz state in Redis and broadcasts."""
        quiz_key = f"{QUIZ_STATE_PREFIX}{quiz_id}"
        quiz_data = await self.get_quiz_state(quiz_id)
        if not quiz_data:
            return None # Quiz not found

        players = quiz_data.setdefault("players", {})
        if player_name not in players:
            players[player_name] = {"score": 0}
            quiz_data["players"] = players
            await self.redis.set(quiz_key, json.dumps(quiz_data))
            logger.info(f"Player {player_name} added to quiz {quiz_id}.")
        else:
             logger.warning(f"Player {player_name} already in quiz {quiz_id}. Rejoining.")

        await self.publish_message(quiz_id, "PLAYER_JOINED", {
            "player": player_name,
            "leaderboard": await self.get_leaderboard(quiz_id)
        })
        return quiz_data

    async def submit_answer(self, submission: AnswerSubmission) -> Optional[bool]:
        """Processes an answer using the AnswerSubmission schema."""
        quiz_id = submission.quiz_id
        player_name = submission.player_name
        question_id = submission.question_id
        selected_option_index = submission.selected_option_index

        quiz_key = f"{QUIZ_STATE_PREFIX}{quiz_id}"
        quiz_data = await self.get_quiz_state(quiz_id)

        if not quiz_data or player_name not in quiz_data.get("players", {}):
            logger.error(f"Quiz or player not found for answer submission: {quiz_id}, {player_name}")
            return None

        question_dict = next((q for q in quiz_data.get("questions", []) if q.get("id") == question_id), None)
        if not question_dict:
            logger.error(f"Question ID {question_id} not found in quiz {quiz_id}")
            return None

        try:
            question = Question.model_validate(question_dict)
        except Exception:
            logger.exception(f"Failed to validate question data from Redis for question {question_id}")
            return None

        is_correct = (question.correct_answer_index == selected_option_index)

        current_score = quiz_data["players"][player_name].get("score", 0)
        if is_correct:
            current_score += 10
            quiz_data["players"][player_name]["score"] = current_score

        await self.redis.set(quiz_key, json.dumps(quiz_data))

        await self.publish_message(quiz_id, "SCORE_UPDATE", {
            "player": player_name,
            "question_id": question_id,
            "is_correct": is_correct,
            "new_score": current_score,
            "leaderboard": await self.get_leaderboard(quiz_id)
        })
        logger.info(f"Answer submitted by {player_name} for quiz {quiz_id}. Correct: {is_correct}")
        return is_correct

    async def get_leaderboard(self, quiz_id: str) -> List[Dict]:
        """Calculates and returns the leaderboard sorted by score."""
        quiz_data = await self.get_quiz_state(quiz_id)
        if not quiz_data or "players" not in quiz_data:
            return []

        leaderboard_data = sorted(
            [{"player": player, "score": info.get("score", 0)} for player, info in quiz_data["players"].items()],
            key=lambda item: item["score"],
            reverse=True
        )
        return leaderboard_data

    async def subscribe_to_updates(self, quiz_id: str):
        """Subscribes a WebSocket handler task to a specific quiz channel."""
        pubsub = self.redis.pubsub()
        channel_name = f"{PUBSUB_CHANNEL_PREFIX}{quiz_id}"
        try:
            await pubsub.subscribe(channel_name)
            logger.info(f"WebSocket handler subscribed to Redis channel: {channel_name}")
            return pubsub
        except Exception:
            logger.exception(f"Failed to subscribe WebSocket handler to Redis channel: {channel_name}")
            await pubsub.close()
            raise

    async def publish_quiz_generated(self, quiz: Quiz):
        """Publishes the newly generated quiz data to its channel."""
        await self.store_quiz_state(quiz)
        await self.publish_message(quiz.quiz_id, "QUIZ_READY", quiz.model_dump())