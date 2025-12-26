# app/services/adaptive_engine.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.models import Player, Quiz, Answer

class AdaptiveEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_player_performance(self, player_name: str, topic: str) -> dict:
        """
        Analyzes a player's history for a specific topic.
        Returns a dictionary with accuracy and recommended difficulty.
        """
        # 1. Find all quizzes taken by this player on this topic
        # We join Player -> Quiz to filter by topic
        stmt = (
            select(Answer)
            .join(Player, Answer.player_id == Player.id)
            .join(Quiz, Player.quiz_id == Quiz.id)
            .where(
                Player.player_name == player_name,
                Quiz.topic.ilike(f"%{topic}%") # Fuzzy match for topic
            )
        )
        
        result = await self.db.execute(stmt)
        answers = result.scalars().all()

        if not answers:
            return None # No history found

        # 2. Calculate Metrics
        total_questions = len(answers)
        correct_answers = sum(1 for a in answers if a.is_correct)
        
        if total_questions == 0:
            return None

        accuracy = (correct_answers / total_questions) * 100
        
        # 3. Determine Adaptive Difficulty
        recommended_difficulty = "medium"
        advice = "Maintain current difficulty."
        
        if accuracy < 50:
            recommended_difficulty = "easy"
            advice = "Player is struggling. Focus on fundamental concepts and simpler questions."
        elif accuracy > 80:
            recommended_difficulty = "hard"
            advice = "Player is proficient. Challenge them with advanced edge cases and complex reasoning."

        return {
            "player_name": player_name,
            "topic": topic,
            "total_questions": total_questions,
            "accuracy": round(accuracy, 2),
            "recommended_difficulty": recommended_difficulty,
            "adaptive_prompt_instruction": advice
        }