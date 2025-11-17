# app/main.py (Corrected for Day 4 and Relative Imports)

import os
from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# --- FIX: Use relative imports ---
from .quiz_manager import QuizManager
from .llm_client import call_ollama_or_fallback
from .schemas import Quiz as QuizSchema, QuizGenerationRequest
from .models import Quiz as QuizModel
# --- END FIX ---
import asyncio
import uvicorn
import logging

# --- DB IMPORTS (Use relative imports) ---
from .db import database, get_db_session, Base, engine
from sqlalchemy.ext.asyncio import AsyncSession
# --- END DB IMPORTS ---

# --- ROUTER IMPORTS (Use relative imports) ---
from .api.submission_routes import router as submission_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")

app = FastAPI(title="Adaptive Learning Agent")
quiz_manager = QuizManager(REDIS_URL) # Use one global instance

# --- FIX: Use relative paths to 'static' and 'templates' folders ---
# These paths are relative to where main.py is (i.e., inside the 'app' folder)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(submission_router)

# --- DATABASE LIFECYCLE EVENTS ---
@app.on_event("startup")
async def startup_event():
    try:
        await database.connect()
        logger.info("Database connection established.")
        # Create tables on startup
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created.")
    except Exception as e:
        logger.critical(f"FATAL: Could not connect to database: {e}", exc_info=True)
    
    await quiz_manager.start_listener()

@app.on_event("shutdown")
async def shutdown_event():
    await database.disconnect()
    logger.info("Database connection closed.")
# --- END LIFECYCLE EVENTS ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # This route serves the main entry page (index.html)
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/quiz/{quiz_id}", response_class=HTMLResponse)
async def get_quiz_page(request: Request, quiz_id: str):
     return templates.TemplateResponse("quiz.html", {"request": request, "quiz_id": quiz_id})

# --- WebSocket ---
@app.websocket("/ws/{quiz_id}")
async def websocket_endpoint(websocket: WebSocket, quiz_id: str):
    await quiz_manager.connect(quiz_id, websocket)
    pubsub = None 
    listener_task = None
    try:
        pubsub = await quiz_manager.subscribe_to_updates(quiz_id)
        
        async def redis_listener(pubsub_conn, ws):
             try:
                 async for message in pubsub_conn.listen():
                      if message["type"] == "message":
                           await ws.send_text(message['data'])
             except Exception: logger.exception(f"WS {quiz_id}: Error in Redis listener.")
             finally: logger.info(f"WS {quiz_id}: Redis listener task finished.")

        listener_task = asyncio.create_task(redis_listener(pubsub, websocket))
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect: logger.info(f"WS {quiz_id}: Client disconnected.")
    except Exception: logger.exception(f"WS {quiz_id}: Error in WebSocket endpoint.")
    finally:
        if listener_task: listener_task.cancel()
        if pubsub: await pubsub.close()
        await quiz_manager.disconnect(quiz_id, websocket)

# --- POST /quizzes (Updated to write to DB) ---
@app.post("/quizzes", response_model=QuizSchema)
async def create_quiz_endpoint(
    request: QuizGenerationRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    topic = request.topic
    difficulty = request.difficulty
    
    quiz_pydantic: QuizSchema = await call_ollama_or_fallback(topic, difficulty) 
    
    try:
        existing_quiz = await db.get(QuizModel, quiz_pydantic.quiz_id)
        if existing_quiz:
             logger.warning(f"Quiz ID {quiz_pydantic.quiz_id} already exists in DB. Skipping save.")
        else:
            db_quiz = QuizModel(
                id=quiz_pydantic.quiz_id,
                topic=quiz_pydantic.topic,
                difficulty=quiz_pydantic.difficulty,
                questions=quiz_pydantic.model_dump()["questions"]
            )
            db.add(db_quiz)
            await db.commit()
            await db.refresh(db_quiz)
            logger.info(f"API: Successfully saved quiz {db_quiz.id} to PostgreSQL.")
            
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to save quiz to DB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save quiz to database.")

    # Store in Redis *after* successful DB save
    await quiz_manager.store_quiz_state(quiz_pydantic)
    
    logger.info(f"API: Generated and stored quiz {quiz_pydantic.quiz_id} for topic {topic}")
    return quiz_pydantic

if __name__ == "__main__":
    # This part is only for local dev, not for Docker
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)), reload=True)