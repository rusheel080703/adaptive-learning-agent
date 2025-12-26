# app/schemas.py
from pydantic import BaseModel, Field, conint
from typing import List, Optional, Dict

# --- Existing Day 1 Schemas ---
class Question(BaseModel):
    id: str = Field(..., description="Unique ID for the question (UUID string)")
    question_text: str
    options: List[str] = Field(..., min_length=4, max_length=4)
    correct_answer_index: conint(ge=0, le=3) # Correct field name
    explanation: Optional[str] = None
    metadata: Optional[Dict] = {}

class Quiz(BaseModel):
    quiz_id: str
    topic: str
    difficulty: str
    questions: List[Question]
    time_limit_seconds: Optional[int] = 600
    created_by: Optional[str] = None

# app/schemas.py (Update this specific class)
class QuizGenerationRequest(BaseModel):
    topic: str
    # We keep difficulty as a manua l override option, but adaptive logic might ignore it
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    # NEW: Optional player name to trigger adaptive logic
    player_name: Optional[str] = None

# --- NEW Day 3/4 Schemas ---
class AnswerSubmission(BaseModel):
    quiz_id: str
    player_name: str # Using simple name for Day 3
    question_id: str # Question ID is a string
    selected_option_index: conint(ge=0, le=3) # Index chosen by player

class PlayerScore(BaseModel): # Model for leaderboard data
    player_name: str
    score: int

class LeaderboardEntry(BaseModel):
    player: str
    score: int

class Leaderboard(BaseModel):
    quiz_id: str
    leaderboard: List[LeaderboardEntry]

# --- Schemas for WebSocket Messages (Good Practice) ---
class WebSocketMessage(BaseModel):
    type: str
    data: Dict
    
    

class TopicMastery(BaseModel):
    topic: str
    accuracy: float
    attempts: int
    recommended_difficulty: str
    confidence_level: str  # e.g., "Beginner", "Intermediate"

class PlayerAnalyticsResponse(BaseModel):
    player_name: str
    total_quizzes: int
    average_score: float
    topic_breakdown: List[TopicMastery]