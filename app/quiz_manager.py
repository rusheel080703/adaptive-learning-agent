# app/quiz_manager.py (Corrected and with Logging)
import json
import asyncio
from typing import Dict, Set, List # Added List
from fastapi import WebSocket
import redis.asyncio as redis
import os
import logging # Added logging import
from uuid import uuid4 # Added uuid import

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Correctly use the Docker network Redis URL
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
PUBSUB_CHANNEL_PREFIX = "quiz_channel:" # Channel for general quiz updates, e.g., new quiz published

class QuizManager:
    """
    Manages WebSocket connections and Redis Pub/Sub for multiple quiz rooms.
    Uses specific channels per quiz_id for score updates.
    """
    def __init__(self, redis_url: str = REDIS_URL):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        # Store connections per quiz_id: Dict[quiz_id, Set[WebSocket]]
        self.connections: Dict[str, Set[WebSocket]] = {}
        self._pubsub_task = None
        logger.info(f"QuizManager initialized with Redis URL: {redis_url}")

    async def start_listener(self):
        """Starts the background Redis PubSub listener task."""
        if self._pubsub_task and not self._pubsub_task.done():
            logger.info("PubSub listener already running.")
            return
        logger.info("Starting Redis PubSub listener...")
        self._pubsub_task = asyncio.create_task(self._listen_pubsub())
        # Add error handling for the listener task
        self._pubsub_task.add_done_callback(self._handle_listener_completion)

    def _handle_listener_completion(self, task: asyncio.Task):
        """Callback to log if the listener task stops unexpectedly."""
        try:
            task.result() # Raises exception if the task failed
            logger.info("PubSub listener task finished cleanly.")
        except asyncio.CancelledError:
            logger.info("PubSub listener task was cancelled.")
        except Exception:
            logger.exception("PubSub listener task failed unexpectedly!")
            # Optionally, attempt to restart the listener here
            # asyncio.create_task(self.start_listener())

    async def _listen_pubsub(self):
        """Listens to all quiz channels on Redis and broadcasts messages."""
        async with self.redis.pubsub() as ps: # Use async context manager
            # Use psubscribe for pattern matching
            await ps.psubscribe(f"{PUBSUB_CHANNEL_PREFIX}*")
            logger.info(f"Subscribed to Redis channels pattern: {PUBSUB_CHANNEL_PREFIX}*")
            while True: # Keep listening indefinitely
                try:
                    message = await ps.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message is None:
                        await asyncio.sleep(0.01) # Short sleep if no message
                        continue

                    logger.info(f"Received Redis message: {message}")
                    if message.get("type") == "pmessage": # Check type for psubscribe
                        channel = message.get("channel")
                        data = message.get("data")
                        if isinstance(data, bytes):
                            data = data.decode()
                        logger.info(f"Attempting broadcast on channel: {channel} with data: {data}")
                        await self._broadcast_channel(channel, data)
                except redis.ConnectionError:
                     logger.error("Redis connection error in listener. Attempting to reconnect...")
                     await asyncio.sleep(5) # Wait before retrying (prevents tight loop on persistent failure)
                     # The pubsub object might need re-subscription after connection loss
                     # Consider adding re-subscription logic here or restarting the listener
                     await ps.psubscribe(f"{PUBSUB_CHANNEL_PREFIX}*") # Re-subscribe attempt
                except Exception:
                    logger.exception("Error in Redis listener loop.")
                    await asyncio.sleep(1) # Prevent tight loop on other errors

    async def _broadcast_channel(self, channel: str, data: str):
        """Sends data to all WebSockets connected to a specific quiz_id."""
        # Ensure channel starts with the prefix
        if not channel.startswith(PUBSUB_CHANNEL_PREFIX):
            logger.warning(f"Ignoring message from unexpected channel: {channel}")
            return

        try:
            # --- THE FIX: Clean the channel name ---
            # Remove the prefix first
            quiz_id_part = channel.split(PUBSUB_CHANNEL_PREFIX, 1)[1]
            # Remove potential leading/trailing angle brackets or other unwanted chars
            quiz_id = quiz_id_part.strip('<>') 
            # --- END FIX ---
            
            # Now, use the cleaned quiz_id to find connections
            active_connections = self.connections.get(quiz_id, set())
            if not active_connections:
                 logger.info(f"No active WebSocket connections for quiz_id: {quiz_id} (cleaned from channel {channel})") # Add cleaned ID log
                 return

            logger.info(f"Broadcasting to {len(active_connections)} connections for quiz_id: {quiz_id}")

            # Use asyncio.gather for concurrent sends
            tasks = [self._send_to_websocket(ws, data, quiz_id) for ws in active_connections]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results to find disconnected clients
            disconnects = []
            valid_connections_list = list(active_connections) # Create a list for indexing
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Ensure index is valid before accessing list
                    if i < len(valid_connections_list):
                        ws_to_disconnect = valid_connections_list[i]
                        disconnects.append(ws_to_disconnect)
                        logger.warning(f"Failed to send to client for quiz {quiz_id}, marking for disconnect. Error: {result}")
                    else:
                        logger.error(f"Index error during disconnect processing for quiz {quiz_id}. Index: {i}, Connections: {len(valid_connections_list)}")


            # Disconnect failed connections outside the loop
            if disconnects:
                 await asyncio.gather(*(self.disconnect(quiz_id, ws) for ws in disconnects))

        except IndexError:
            logger.error(f"Could not extract quiz_id cleanly from channel part: {quiz_id_part} (original channel: {channel})")
        except Exception:
             logger.exception(f"Unexpected error during broadcast for channel: {channel}")


    async def _send_to_websocket(self, websocket: WebSocket, data: str, quiz_id: str):
        """Safely sends data to a single WebSocket client."""
        try:
            await websocket.send_text(data)
            # --- ADD LOGGING CONFIRMATION ---
            logger.info(f"Successfully sent data via WebSocket for quiz {quiz_id}")
            # --- END LOGGING ---
        except Exception as e:
            # Raise to be caught by gather
            raise e

    async def _send_to_websocket(self, websocket: WebSocket, data: str, quiz_id: str):
        """Safely sends data to a single WebSocket client."""
        try:
            await websocket.send_text(data)
            logger.debug(f"Sent data to WebSocket client for quiz {quiz_id}") # Use debug level
        except Exception as e:
            # Don't log full trace here, just raise to be caught by gather
            raise e

    async def connect(self, quiz_id: str, websocket: WebSocket):
        """Accepts a WebSocket connection and adds it to the quiz room."""
        await websocket.accept()
        self.connections.setdefault(quiz_id, set()).add(websocket)
        logger.info(f"Client connected to quiz_id: {quiz_id}. Total connections for this quiz: {len(self.connections.get(quiz_id, set()))}")

    async def disconnect(self, quiz_id: str, websocket: WebSocket):
        """Removes a WebSocket connection from the quiz room and closes it."""
        conns = self.connections.get(quiz_id)
        connection_removed = False
        if conns and websocket in conns:
            conns.remove(websocket)
            connection_removed = True
            logger.info(f"Client disconnected from quiz_id: {quiz_id}. Remaining connections: {len(conns) if conns else 0}")
            if not conns: # Clean up empty sets
                del self.connections[quiz_id]
                logger.info(f"Removed empty connection set for quiz_id: {quiz_id}")

        # Attempt to close only if the connection wasn't already closed by the client
        try:
            # Check state before closing - less standard, relies on internals
            # A more robust check might involve trying a ping first
             if websocket.client_state.name == 'CONNECTED': # Example check
                 await websocket.close()
                 logger.debug(f"Closed WebSocket connection server-side for quiz {quiz_id}")
        except RuntimeError as e:
             # Catch errors if the connection is already closing/closed
             if "WebSocket is not connected" in str(e):
                 logger.debug(f"WebSocket for quiz {quiz_id} already closed by client.")
             else:
                 logger.warning(f"Error closing WebSocket for quiz {quiz_id}: {e}")
        except Exception:
            # Ignore other potential errors during close
            logger.exception(f"Unexpected error closing WebSocket for quiz {quiz_id}")
            pass
        
        # Log if disconnect was called but connection wasn't found (might indicate race condition)
        # if not connection_removed:
        #      logger.warning(f"Attempted to disconnect client not found in active connections for quiz_id: {quiz_id}")


    async def publish_quiz(self, quiz_id: str, payload: dict):
        """Publishes the initial quiz or updates to the specific quiz channel."""
        channel = f"{PUBSUB_CHANNEL_PREFIX}{quiz_id}"
        message = json.dumps({"type": "QUIZ_DATA", **payload}) # Add a type field
        logger.info(f"Publishing quiz data to Redis channel: {channel}")
        await self.redis.publish(channel, message)

    # --- Placeholder Methods (As defined in ChatGPT Plan) ---
    async def create_quiz(self, title: str, questions: List[Dict]):
        """Placeholder: Logic to create and store quiz details (e.g., in Redis hash)."""
        quiz_id = str(uuid4())
        quiz_data = {"title": title, "questions": questions, "players": {}, "state": "lobby"}
        # Example using Redis Hash (better than plain SET for structured data)
        await self.redis.hset(f"quiz_details:{quiz_id}", mapping=quiz_data)
        logger.info(f"Created quiz details in Redis for quiz_id: {quiz_id}")
        return quiz_id

    async def join_quiz(self, quiz_id: str, player_name: str):
        """Placeholder: Adds a player to a quiz and broadcasts update."""
        # This logic would ideally use Redis Hash operations for atomicity
        key = f"quiz_details:{quiz_id}"
        player_key = f"players.{player_name}" # Example for nested update if supported or handled manually
        
        # Simplified: Get, Update, Set (Not atomic, risk of race condition)
        quiz_data_str = await self.redis.get(key.replace("details","")) # Assuming it was set with plain SET earlier
        if not quiz_data_str:
             logger.error(f"Quiz not found: {quiz_id}")
             return None # Or raise exception
        quiz_data = json.loads(quiz_data_str)

        if player_name not in quiz_data.get("players", {}):
            quiz_data.setdefault("players", {})[player_name] = {"score": 0}
            await self.redis.set(key.replace("details",""), json.dumps(quiz_data)) # Update the whole object

            # Broadcast player join event
            channel = f"{PUBSUB_CHANNEL_PREFIX}{quiz_id}"
            update_message = json.dumps({"type": "PLAYER_JOINED", "player": player_name, "quiz_state": quiz_data})
            await self.redis.publish(channel, update_message)
            logger.info(f"Player {player_name} joined quiz {quiz_id}. Published update.")
            return quiz_data
        else:
             logger.warning(f"Player {player_name} already in quiz {quiz_id}.")
             return quiz_data


    async def submit_answer(self, quiz_id: str, player_name: str, question_idx: int, is_correct: bool):
        """Placeholder: Updates score and broadcasts leaderboard/score update."""
        # Again, ideally use atomic Redis operations (e.g., HINCRBY for score)
        key = f"quiz_details:{quiz_id}"
        
        # Simplified Get-Update-Set
        quiz_data_str = await self.redis.get(key.replace("details","")) # Assuming plain SET
        if not quiz_data_str:
             logger.error(f"Quiz not found for answer submission: {quiz_id}")
             return None
        quiz_data = json.loads(quiz_data_str)
        
        player_data = quiz_data.get("players", {}).get(player_name)
        if not player_data:
             logger.error(f"Player {player_name} not found in quiz {quiz_id} for answer submission.")
             return None

        if is_correct:
            player_data["score"] = player_data.get("score", 0) + 10 # Example scoring

        # Update player score in the main quiz data structure
        quiz_data["players"][player_name] = player_data
        await self.redis.set(key.replace("details",""), json.dumps(quiz_data)) # Update the whole object

        # Broadcast score update event
        channel = f"{PUBSUB_CHANNEL_PREFIX}{quiz_id}"
        # Send only relevant info, or the whole state if needed by frontend
        update_message = json.dumps({
            "type": "SCORE_UPDATE",
            "player": player_name,
            "new_score": player_data["score"],
            "leaderboard": sorted( # Example leaderboard generation
                 [(p, d.get("score", 0)) for p, d in quiz_data.get("players", {}).items()],
                 key=lambda item: item[1],
                 reverse=True
             )
        })
        await self.redis.publish(channel, update_message)
        logger.info(f"Score updated for player {player_name} in quiz {quiz_id}. Published update.")
        return quiz_data.get("players")

    async def subscribe_to_updates(self, quiz_id: str):
        """Subscribes a WebSocket handler task to a specific quiz channel."""
        pubsub = self.redis.pubsub()
        channel_name = f"{PUBSUB_CHANNEL_PREFIX}{quiz_id}"
        await pubsub.subscribe(channel_name)
        logger.info(f"WebSocket handler subscribed to Redis channel: {channel_name}")
        return pubsub