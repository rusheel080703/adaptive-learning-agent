# Adaptive Learning Agent (MVP) — Day 1

This repo contains the Day-1 starter skeleton for the Adaptive Learning Agent Platform.

## Quick start (local)

1. Copy `.env.example` to `.env` and edit if needed.
2. Start Redis: `docker run -p 6379:6379 redis:7`
3. Create virtualenv and install deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
