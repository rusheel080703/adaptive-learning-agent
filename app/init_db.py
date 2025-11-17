# app/init_db.py
import asyncio
from app.db import engine, Base # Correct import from app.db

async def init_db():
    print("Attempting to initialize database... creating all tables.")
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Uncomment to wipe DB on init
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created successfully.")
    await engine.dispose()

if __name__ == "__main__":
    # This check ensures the code only runs when you execute 'python -m app.init_db'
    # We must add this check to prevent errors
    import os
    # We need to add the parent directory to the path to fix 'app.db' import
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.db import engine, Base
    
    asyncio.run(init_db())