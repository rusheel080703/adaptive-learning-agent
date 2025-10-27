# app/main.py
import os
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from app.quiz_manager import QuizManager
from app.llm_client import call_ollama_or_fallback
from app.schemas import Quiz
import asyncio

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

app = FastAPI(title="Adaptive Learning Agent — MVP")
quiz_manager = QuizManager(REDIS_URL)

@app.on_event("startup")
async def startup_event():
    # start Redis pubsub listener in background
    await quiz_manager.start_listener()

@app.get("/")
async def root():
    return {"status": "ok", "msg": "Adaptive Learning Agent API"}

@app.websocket("/ws/{quiz_id}")
async def websocket_endpoint(websocket: WebSocket, quiz_id: str):
    # Minimal: accept without auth for Day 1
    await quiz_manager.connect(quiz_id, websocket)
    try:
        while True:
            # keep connection alive and echo pings
            text = await websocket.receive_text()
            await websocket.send_text(f"server echo: {text}")
    except WebSocketDisconnect:
        await quiz_manager.disconnect(quiz_id, websocket)
    except Exception:
        await quiz_manager.disconnect(quiz_id, websocket)

@app.post("/quizzes")
async def create_quiz(payload: dict):
    topic = payload.get("topic")
    difficulty = payload.get("difficulty", "medium")
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")
    quiz = await call_ollama_or_fallback(topic, difficulty)
    # TODO: persist to DB later
    await quiz_manager.publish_quiz(quiz.quiz_id, quiz.dict())
    return JSONResponse(content={"quiz_id": quiz.quiz_id})

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
