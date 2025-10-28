# app/main.py (FINAL CORRECTED PATHS)

import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.quiz_manager import QuizManager
from app.llm_client import call_ollama_or_fallback
from app.schemas import Quiz
import asyncio
import uvicorn

# Ensure we use the correct Docker networking URL
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")

# APP Initialization
app = FastAPI(title="Adaptive Learning Agent")
quiz_manager = QuizManager(REDIS_URL)

# --- 1. STATIC FILE & TEMPLATE SETUP (THE FIX) ---
# FIX: The 'static' folder is inside the 'app' directory,
# so the path relative to the container's working directory (/app) is 'app/static'.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# FIX: The templates folder is also inside the 'app' directory.
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
async def startup_event():
    # start Redis pubsub listener in background
    await quiz_manager.start_listener()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # This serves the index.html template
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws/{quiz_id}")
async def websocket_endpoint(websocket: WebSocket, quiz_id: str):
    # Minimal: accept without auth for Day 1
    await quiz_manager.connect(quiz_id, websocket)
    try:
        while True:
            # keep connection alive and echo pings
            text = await websocket.receive_text()
            # For Day 2, we just echo. Later, this receives the answer JSON.
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
        
    # 1. GENERATE QUIZ (Primary AI Task)
    quiz = await call_ollama_or_fallback(topic, difficulty) 
    
    # 2. PUBLISH TO REDIS (The Real-Time Notification)
    await quiz_manager.publish_quiz(quiz.quiz_id, quiz.model_dump()) 
    
    return JSONResponse(content={"quiz_id": quiz.quiz_id, "status": "Quiz published for room: " + quiz.quiz_id})

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))