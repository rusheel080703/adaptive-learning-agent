# app/db.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from databases import Database

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@db:5432/quizdb")

# 'databases' library instance for simple connect/disconnect in main.py
database = Database(DATABASE_URL) 
# SQLAlchemy engine for ORM operations
engine = create_async_engine(DATABASE_URL) 

# Async sessionmaker
async_session = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# Base class for our ORM models in models.py
Base = declarative_base()

async def get_db_session() -> AsyncSession:
    """FastAPI dependency to get an async database session."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()