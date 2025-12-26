# app/services/analytics_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, Integer  # <--- ADDED Integer here
from app.models import Player, Quiz, Answer
from typing import List, Dict

class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_player_analytics(self, player_name: str) -> Dict:
        """
        Aggregates raw quiz data into high-level insights using efficient SQL.
        """
        # 1. Get Basic Stats (Total Quizzes, Avg Score)
        stmt_basic = (
            select(
                func.count(Player.id),
                func.avg(Player.score)
            )
            .where(Player.player_name == player_name)
        )
        result_basic = await self.db.execute(stmt_basic)
        # Handle case where player has no history
        row = result_basic.one()
        total_quizzes = row[0]
        avg_score = row[1]

        if not total_quizzes or total_quizzes == 0:
            return None # Player not found or no quizzes

        # 2. Get Topic-Wise Performance
        # FIX: We use 'Integer' instead of 'int' in the cast function
        stmt_topics = (
            select(
                Quiz.topic,
                func.count(Answer.id).label("total_answers"),
                func.sum(func.cast(Answer.is_correct, Integer)).label("correct_answers")
            )
            .join(Player, Answer.player_id == Player.id)
            .join(Quiz, Player.quiz_id == Quiz.id)
            .where(Player.player_name == player_name)
            .group_by(Quiz.topic)
        )
        
        result_topics = await self.db.execute(stmt_topics)
        topic_rows = result_topics.all()

        # 3. Process Topic Data (Python Logic)
        topic_breakdown = []
        for topic, total, correct in topic_rows:
            # Handle potential None values if no answers exist
            correct_count = correct if correct else 0
            
            accuracy = (correct_count / total) * 100 if total > 0 else 0
            
            # Determine Confidence Level
            if accuracy < 50:
                confidence = "Beginner"
                rec_diff = "easy"
            elif accuracy < 80:
                confidence = "Intermediate"
                rec_diff = "medium"
            else:
                confidence = "Expert"
                rec_diff = "hard"

            topic_breakdown.append({
                "topic": topic,
                "accuracy": round(accuracy, 1),
                "attempts": total,
                "recommended_difficulty": rec_diff,
                "confidence_level": confidence
            })

        return {
            "player_name": player_name,
            "total_quizzes": total_quizzes,
            "average_score": round(avg_score, 1) if avg_score else 0,
            "topic_breakdown": topic_breakdown
        }