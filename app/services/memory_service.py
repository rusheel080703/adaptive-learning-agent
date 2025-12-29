# app/services/memory_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from app.models import PlayerProfile
from app.services.analytics_service import AnalyticsService
import datetime

class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.analytics = AnalyticsService(db)

    async def get_or_create_profile(self, player_name: str) -> PlayerProfile:
        """Fetch existing profile or create a blank one."""
        stmt = select(PlayerProfile).where(PlayerProfile.player_name == player_name)
        result = await self.db.execute(stmt)
        profile = result.scalars().first()
        
        if not profile:
            profile = PlayerProfile(player_name=player_name)
            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)
        
        return profile

    async def update_learning_profile(self, player_name: str):
        """
        The Core Logic: Analyzes history to detect patterns and update the persistent profile.
        """
        # 1. Get the raw numbers from Day 6 Analytics
        stats = await self.analytics.get_player_analytics(player_name)
        if not stats or not stats["topic_breakdown"]:
            return None

        # 2. Analyze Weaknesses & Strengths
        weak_list = []
        strong_list = []
        
        for topic_data in stats["topic_breakdown"]:
            topic = topic_data["topic"]
            acc = topic_data["accuracy"]
            attempts = topic_data["attempts"]

            # Only judge if they've tried at least 3 questions
            if attempts >= 3:
                if acc < 40:
                    weak_list.append(topic)
                elif acc > 80:
                    strong_list.append(topic)

        # 3. Determine Strategy
        # Strategy Logic:
        # - If many weaknesses -> "Concept-First" (Slow down, explain more)
        # - If many strengths -> "Challenge-Mode" (Give harder edge cases)
        # - Else -> "Standard"
        strategy = "Standard"
        if len(weak_list) > 0:
            strategy = "Concept-First"
        elif len(strong_list) > 2:
            strategy = "Challenge-Mode"

        # 4. Save to Database
        profile = await self.get_or_create_profile(player_name)
        profile.weak_topics = ",".join(weak_list)
        profile.strong_topics = ",".join(strong_list)
        profile.current_strategy = strategy
        profile.last_updated = str(datetime.datetime.now())
        
        await self.db.commit()
        await self.db.refresh(profile)
        
        return profile