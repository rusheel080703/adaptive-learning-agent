# app/api/submission_routes.py (Corrected for Day 4)
from fastapi import APIRouter, HTTPException, Depends
# --- FIX: Use relative imports ---
from ..quiz_manager import QuizManager
from ..schemas import AnswerSubmission, Quiz as QuizSchema
import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload

# --- DB IMPORTS ---
from ..db import get_db_session
from ..models import Quiz as QuizModel
from ..models import Player as PlayerModel
from ..models import Answer as AnswerModel
# --- END DB IMPORTS ---

logger = logging.getLogger(__name__)

# --- Dependency Injection for QuizManager ---
# We get the global instance from main.py
def get_quiz_manager():
    # This import must be local to avoid circular dependency at startup
    from ..main import quiz_manager as global_quiz_manager 
    return global_quiz_manager
# --- End DI Setup ---

router = APIRouter(prefix="/quiz", tags=["Quiz Gameplay"])

@router.post("/join/{quiz_id}")
async def join_quiz_endpoint(
    quiz_id: str, 
    player_name: str, 
    quiz_manager: QuizManager = Depends(get_quiz_manager),
    db: AsyncSession = Depends(get_db_session)
):
    """Adds a player to Redis (live state) and PostgreSQL (permanent record)."""
    
    quiz_obj = await db.get(QuizModel, quiz_id)
    if not quiz_obj:
        raise HTTPException(status_code=404, detail=f"Quiz '{quiz_id}' not found in persistent database.")

    stmt = select(PlayerModel).where(
        PlayerModel.quiz_id == quiz_id,
        PlayerModel.player_name == player_name
    )
    result = await db.execute(stmt)
    db_player = result.scalars().first()
    
    player_id_to_return = 0
    
    if not db_player:
        db_player = PlayerModel(
            player_name=player_name,
            quiz_id=quiz_id,
            score=0
        )
        db.add(db_player)
        await db.commit()
        await db.refresh(db_player)
        player_id_to_return = db_player.id
        logger.info(f"API: Player {player_name} (ID: {player_id_to_return}) permanently saved for quiz {quiz_id}.")
    else:
        player_id_to_return = db_player.id
        logger.info(f"API: Player {player_name} (ID: {player_id_to_return}) rejoining quiz {quiz_id}.")

    quiz_state = await quiz_manager.join_quiz(quiz_id, player_name)
    if quiz_state is None:
        logger.warning(f"Quiz {quiz_id} not in Redis. Re-caching from DB.")
        # Convert SQL model back to Pydantic schema
        quiz_pydantic = QuizSchema.model_validate(quiz_obj, from_attributes=True) 
        await quiz_manager.store_quiz_state(quiz_pydantic)
        quiz_state = await quiz_manager.join_quiz(quiz_id, player_name) # Try joining again
        
    if quiz_state is None:
         raise HTTPException(status_code=500, detail="Failed to join quiz after re-caching.")

    return {"message": f"Player '{player_name}' joined quiz '{quiz_id}'.", "player_id": player_id_to_return}

@router.post("/submit")
async def submit_answer_endpoint(
    submission: AnswerSubmission, 
    quiz_manager: QuizManager = Depends(get_quiz_manager),
    db: AsyncSession = Depends(get_db_session)
):
    """Submits answer to Redis (live) and saves to PostgreSQL (permanent)."""
    
    is_correct = await quiz_manager.submit_answer(submission)
    if is_correct is None:
        raise HTTPException(status_code=404, detail="Quiz, player, or question not found in Redis state.")

    try:
        stmt_player = select(PlayerModel).where(
            PlayerModel.quiz_id == submission.quiz_id,
            PlayerModel.player_name == submission.player_name
        )
        result_player = await db.execute(stmt_player)
        db_player = result_player.scalars().first()
        
        if not db_player:
             raise HTTPException(status_code=404, detail="Player not found in database.")

        db_answer = AnswerModel(
            player_id=db_player.id,
            question_id=submission.question_id,
            selected_option_index=submission.selected_option_index,
            is_correct=is_correct
        )
        db.add(db_answer)
        
        if is_correct:
            await db.refresh(db_player, ["score"]) 
            db_player.score = (db_player.score or 0) + 10 
        
        await db.commit()
        logger.info(f"API: Answer from {submission.player_name} saved to DB.")
        
        return {"correct": is_correct}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to save answer to DB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save answer to database.")

@router.get("/leaderboard/{quiz_id}")
async def get_leaderboard_endpoint(quiz_id: str, quiz_manager: QuizManager = Depends(get_quiz_manager)):
    """Gets the LIVE leaderboard from Redis."""
    leaderboard_data = await quiz_manager.get_leaderboard(quiz_id)
    return {"quiz_id": quiz_id, "leaderboard": leaderboard_data}

@router.get("/state/{quiz_id}")
async def get_quiz_state_endpoint(quiz_id: str, quiz_manager: QuizManager = Depends(get_quiz_manager)):
    """Gets the LIVE quiz state from Redis."""
    quiz_state = await quiz_manager.get_quiz_state(quiz_id)
    if not quiz_state:
         raise HTTPException(status_code=404, detail=f"Quiz '{quiz_id}' not found in live state.")
    return quiz_state

# --- NEW Day 4 Endpoint ---
@router.get("/history/{player_name}")
async def get_player_history(player_name: str, db: AsyncSession = Depends(get_db_session)):
    """Gets a player's entire history from PostgreSQL."""
    try:
        stmt = select(PlayerModel).where(
            PlayerModel.player_name == player_name
        ).options(
            joinedload(PlayerModel.answers),
            joinedload(PlayerModel.quiz)
        ).order_by(PlayerModel.id.desc())
        
        result = await db.execute(stmt)
        players = result.scalars().unique().all()
        
        if not players:
            raise HTTPException(status_code=404, detail="Player not found")
        
        history = []
        for player_entry in players:
            if player_entry.quiz:
                history.append({
                    "quiz_id": player_entry.quiz_id,
                    "quiz_topic": player_entry.quiz.topic,
                    "final_score": player_entry.score,
                    "date_played": player_entry.quiz.created_at,
                    "answers": [
                        {
                            "question_id": a.question_id, 
                            "selected_index": a.selected_option_index, 
                            "was_correct": a.is_correct
                        } for a in player_entry.answers
                    ]
                })
            else:
                 logger.warning(f"Player entry {player_entry.id} is missing quiz data.")
        
        return {"player_name": player_name, "quiz_history": history}
    except Exception as e:
         logger.error(f"Failed to fetch player history: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Error fetching player history.")