# app/llm_client.py (Adaptive Update)
import uuid
import logging
import json
from typing import Any, List, Optional, Dict
from .schemas import Quiz
import httpx
import os
from pydantic import ValidationError

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL_NAME = os.environ.get("OLLAMA_MODEL_NAME", "mistral:7b")

async def deterministic_quiz_template(topic: str, difficulty: str) -> Quiz:
    """Fallback generator if LLM fails."""
    qid = str(uuid.uuid4())
    questions_data = [] 
    for i in range(3):
        questions_data.append({
            "id": f"{qid}-{i}",
            "question_text": f"Sample {difficulty} question {i+1} about {topic} (Fallback)", 
            "options": ["A", "B", "C", "D"], 
            "correct_answer_index": 0, 
            "explanation": "This is a fallback question.",
            "metadata": {} 
        })
    return Quiz(quiz_id=qid, topic=topic, difficulty=difficulty, questions=questions_data)

async def call_llm_api(model_name: str, prompt: str, timeout: int) -> dict:
    """Raw API call to Ollama."""
    url = f"{OLLAMA_URL}/api/generate"
    
    # --- IMPROVED SYSTEM PROMPT ---
    system_prompt = """
    You are a strict and precise quiz generator. 
    You must output strictly valid JSON.
    
    CRITICAL RULES:
    1. The 'correct_answer_index' MUST be the 0-based index of the correct option.
    2. Example: If options are ["A", "B", "C", "D"] and "B" is correct, index is 1.
    3. Double-check your math and logic before assigning the index.
    
    Format:
    {
      "quiz_id": "uuid",
      "topic": "string",
      "difficulty": "string",
      "questions": [
        {
          "id": "uuid",
          "question_text": "string",
          "options": ["string", "string", "string", "string"],
          "correct_answer_index": int, 
          "explanation": "string"
        }
      ]
    }
    """
    # ------------------------------

    payload = {
        "model": model_name,
        "prompt": prompt, 
        "system": system_prompt,
        "stream": False,
        "format": "json"
    }

    logger.info(f"Calling LLM: {model_name} with prompt length: {len(prompt)}")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "{}")

async def call_ollama_or_fallback(
    topic: str, 
    difficulty: str, 
    adaptive_data: Optional[Dict] = None, # <--- NEW PARAMETER
    timeout: int = 60
) -> Quiz:
    """
    Generates a quiz, optionally using adaptive player data to adjust the prompt.
    """
    
    # 1. Build the Adaptive Prompt
    if adaptive_data:
        # If we have player history, we override the request's difficulty
        real_difficulty = adaptive_data.get("recommended_difficulty", difficulty)
        advice = adaptive_data.get("adaptive_prompt_instruction", "")
        accuracy = adaptive_data.get("accuracy", 0)
        
        full_prompt = (
            f"Generate a {real_difficulty} quiz about '{topic}'. "
            f"Context: The player has a historical accuracy of {accuracy}% on this topic. "
            f"Instruction: {advice}. "
            f"Ensure questions are tailored to this skill level."
        )
        logger.info(f"Using ADAPTIVE prompt for player {adaptive_data['player_name']}")
    else:
        # Standard generic prompt
        full_prompt = f"Generate a {difficulty} quiz about '{topic}' with 3 questions."

    # 2. Call LLM
    try:
        response_str = await call_llm_api(OLLAMA_MODEL_NAME, full_prompt, timeout)
        
        # Parse JSON
        if isinstance(response_str, str):
            # Cleanup any markdown formatting if present
            clean_str = response_str.strip().strip('```json').strip('```')
            data = json.loads(clean_str)
        else:
            data = response_str

        # Validate with Pydantic
        quiz = Quiz.model_validate(data)
        logger.info("LLM generation successful.")
        return quiz

    except Exception as e:
        logger.warning(f"LLM failed: {e}. Using fallback.", exc_info=True)
        return await deterministic_quiz_template(topic, difficulty)