# app/api/quiz_routes.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, json, logging
# We import QuizManager from the current working directory's path (../quiz_manager)
from app.quiz_manager import QuizManager 

# This creates a module-level instance of QuizManager, assuming REDIS_URL is accessible
# Note: We should pass REDIS_URL, but for routing modules, we often rely on global setup or DI.
# For simplicity and Day 2, we will pull the URL directly and rely on FastAPI startup logic.
import os
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
quiz_manager = QuizManager(REDIS_URL)

router = APIRouter()

@router.websocket("/ws/{quiz_id}")
async def quiz_websocket(websocket: WebSocket, quiz_id: str):
    await websocket.accept()
    # Subscribe to the quiz channel using the dedicated method
    pubsub = await quiz_manager.subscribe_to_updates(quiz_id)

    try:
        # Start the listener task in the background
        async for message in pubsub.listen():
            if message["type"] == "message":
                # Ensure the message is sent back to the client
                await websocket.send_text(message["data"])

    except WebSocketDisconnect:
        # The WebSocket connection closed
        # Note: unsubscribe is handled by the pubsub object's lifecycle in redis.asyncio
        logging.info(f"Client disconnected from quiz {quiz_id}")
    except Exception as e:
        logging.error(f"WebSocket error in quiz {quiz_id}: {e}")

# We will need the POST endpoint from app/main.py, but we'll leave it there 
# for now to avoid disrupting the working LLM call.