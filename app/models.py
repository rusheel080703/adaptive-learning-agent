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