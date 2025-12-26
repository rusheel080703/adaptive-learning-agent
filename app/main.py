# app/main.py (Day 5: Adaptive Logic Wired In)

import os
from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .quiz_manager import QuizManager
from .llm_client import call_ollama_or_fallback
from .schemas import Quiz as QuizSchema, QuizGenerationRequest
from .models import Quiz as QuizModel
# --- NEW IMPORTS ---
from .services.adaptive_engine import AdaptiveEngine
# -------------------
from .services.analytics_service import AnalyticsService
from .schemas import PlayerAnalyticsResponse


import asyncio
import uvicorn
import logging

from .db import database, get_db_session, Base, engine
from sqlalchemy.ext.asyncio import AsyncSession
from .api.submission_routes import router as submission_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")

app = FastAPI(title="Adaptive Learning Agent")
quiz_manager = QuizManager(REDIS_URL)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(submission_router)

@app.on_event("startup")
async def startup_event():
    try:
        await database.connect()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.critical(f"DB Connection failed: {e}")
    await quiz_manager.start_listener()

@app.on_event("shutdown")
async def shutdown_event():
    await database.disconnect()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- NEW DASHBOARD ROUTE ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# --- NEW ANALYTICS API ROUTE ---
@app.get("/analytics/player/{player_name}", response_model=PlayerAnalyticsResponse)
async def get_player_analytics_endpoint(
    player_name: str, 
    db: AsyncSession = Depends(get_db_session)
):
    service = AnalyticsService(db)
    data = await service.get_player_analytics(player_name)
    if not data:
        raise HTTPException(status_code=404, detail="Player stats not found")
    return data

@app.get("/quiz/{quiz_id}", response_class=HTMLResponse)
async def get_quiz_page(request: Request, quiz_id: str):
     return templates.TemplateResponse("quiz.html", {"request": request, "quiz_id": quiz_id})

@app.websocket("/ws/{quiz_id}")
async def websocket_endpoint(websocket: WebSocket, quiz_id: str):
    await quiz_manager.connect(quiz_id, websocket)
    try:
        pubsub = await quiz_manager.subscribe_to_updates(quiz_id)
        async def redis_listener(pubsub_conn, ws):
             async for message in pubsub_conn.listen():
                  if message["type"] == "message":
                       await ws.send_text(message['data'])
        
        asyncio.create_task(redis_listener(pubsub, websocket))
        while True: await websocket.receive_text()
    except Exception: pass
    finally: await quiz_manager.disconnect(quiz_id, websocket)

# --- UPDATED ADAPTIVE ENDPOINT ---
@app.post("/quizzes", response_model=QuizSchema)
async def create_quiz_endpoint(
    request: QuizGenerationRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    topic = request.topic
    difficulty = request.difficulty
    
    # 1. Initialize Adaptive Context
    adaptive_data = None
    
    # 2. If player name is provided, calculate stats
    if request.player_name:
        logger.info(f"Calculating adaptive profile for {request.player_name} on topic {topic}")
        engine_service = AdaptiveEngine(db)
        adaptive_data = await engine_service.get_player_performance(request.player_name, topic)
        
        if adaptive_data:
            logger.info(f"Adaptive Profile Found: Accuracy={adaptive_data['accuracy']}%, Recommended={adaptive_data['recommended_difficulty']}")
        else:
            logger.info("No history found for player. Using standard difficulty.")

    # 3. Call LLM with the extra context
    quiz_pydantic: QuizSchema = await call_ollama_or_fallback(
        topic, 
        difficulty, 
        adaptive_data=adaptive_data # Pass the stats!
    )
    
    # 4. Save to DB (Standard logic)
    try:
        existing_quiz = await db.get(QuizModel, quiz_pydantic.quiz_id)
        if not existing_quiz:
            db_quiz = QuizModel(
                id=quiz_pydantic.quiz_id,
                topic=quiz_pydantic.topic,
                difficulty=quiz_pydantic.difficulty,
                questions=quiz_pydantic.model_dump()["questions"]
            )
            db.add(db_quiz)
            await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"DB Save Error: {e}")

    await quiz_manager.store_quiz_state(quiz_pydantic)
    return quiz_pydantic

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)), reload=True)