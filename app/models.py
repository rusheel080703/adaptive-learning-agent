# app/models.py
from sqlalchemy import Column, Integer, String, JSON, DateTime, func, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base # Import Base from our db.py

class Quiz(Base):
    __tablename__ = "quizzes"
    
    id = Column(String, primary_key=True, index=True) 
    topic = Column(String, index=True)
    difficulty = Column(String)
    questions = Column(JSON) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    players = relationship("Player", back_populates="quiz")

class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, index=True) 
    score = Column(Integer, default=0) 
    
    quiz_id = Column(String, ForeignKey("quizzes.id"))
    
    quiz = relationship("Quiz", back_populates="players")
    answers = relationship("Answer", back_populates="player")

class Answer(Base):
    __tablename__ = "answers"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    
    question_id = Column(String, index=True) 
    selected_option_index = Column(Integer) 
    is_correct = Column(Boolean)
    
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    
    player = relationship("Player", back_populates="answers")
    
class PlayerProfile(Base):
    """
    Long-term memory for a specific player.
    Tracks persistent weaknesses and learning strategies.
    """
    __tablename__ = "player_profiles"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, unique=True, index=True)
    
    # Comma-separated list of topics where accuracy is consistently < 40%
    weak_topics = Column(String, default="") 
    
    # Comma-separated list of topics where accuracy is > 80%
    strong_topics = Column(String, default="")
    
    # The current AI teaching strategy (e.g., "Standard", "Concept-First", "Challenge")
    current_strategy = Column(String, default="Standard")
    
    # Metadata for debugging
    last_updated = Column(String) # Simple timestamp string