# app/llm_client.py
import uuid
import logging
import json
from typing import Any, List
from .schemas import Quiz # <-- FIX: Use relative import
import httpx
import os
from pydantic import ValidationError, BaseModel

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL_NAME = os.environ.get("OLLAMA_MODEL_NAME", "mistral:7b")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL_NAME", "llama3:latest")

async def deterministic_quiz_template(topic: str, difficulty: str) -> Quiz:
    """Simple deterministic fallback that creates a 3-question quiz."""
    qid = str(uuid.uuid4())
    questions_data = [] 
    for i in range(3):
        questions_data.append({
            "id": f"{qid}-{i}",
            "question_text": f"Sample {difficulty} question {i+1} about {topic}", 
            "options": ["A", "B", "C", "D"], 
            "correct_answer_index": 0, 
            "explanation": f"Explanation for question {i+1}",
            "metadata": {} 
        })
    
    try:
        quiz_obj = Quiz(
            quiz_id=qid,
            topic=topic,
            difficulty=difficulty,
            questions=questions_data 
        )
        return quiz_obj
    except ValidationError as e:
        logger.error("Pydantic validation failed INSIDE deterministic template!", exc_info=True)
        return Quiz(quiz_id=str(uuid.uuid4()), topic="Error", difficulty="error", questions=[])


async def call_llm_api(model_name: str, prompt: str, timeout: int) -> dict:
    """Handles the actual API call to the Ollama endpoint."""
    url = f"{OLLAMA_URL}/api/generate"

    system_prompt = f"""
    You are an expert quiz generator. Your task is to generate a quiz STRICTLY in JSON format based on the user's request.
    The output MUST be a single, valid JSON object conforming precisely to the following structure:
    {{
      "quiz_id": "string (generate uuid)",
      "topic": "string",
      "difficulty": "string (e.g., 'easy', 'medium', 'hard')",
      "questions": [
        {{
          "id": "string (generate unique id)",
          "question_text": "string (the question)",
          "options": ["string", "string", "string", "string"],
          "correct_answer_index": integer (0-3),
          "explanation": "string (optional explanation)",
          "metadata": {{}}
        }}
      ]
    }}
    Do NOT include any preamble, commentary, markdown fences (```json), or any text outside the main JSON object.
    The quiz must contain exactly 3 questions about the topic: {prompt}.
    """

    payload = {
        "model": model_name,
        "prompt": f"User Request: {prompt}", 
        "system": system_prompt,
        "stream": False,
        "format": "json"
    }

    logger.info("Attempting LLM call to %s with model %s", url, model_name)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        raw_response = resp.json()

        try:
            json_str = raw_response.get("response", "{}")
            if isinstance(json_str, str):
                cleaned_json_str = json_str.strip().strip('```json').strip('```')
                data = json.loads(cleaned_json_str) 
                return data
            elif isinstance(json_str, dict):
                 return json_str
            else:
                 return raw_response
                 
        except json.JSONDecodeError as json_err:
            logger.error("Failed to decode JSON from LLM response string: %s", json_str, exc_info=True)
            raise ValueError(f"Invalid JSON output structure from LLM: {json_err}") from json_err
        except Exception as e:
             logger.error("Unexpected error parsing LLM response.", exc_info=True)
             raise ValueError("Unexpected error processing LLM output.") from e


async def call_ollama_or_fallback(topic: str, difficulty: str, timeout: int = 60) -> Quiz:
    """
    Tries primary LLM (Mistral), logs detailed errors, then uses Deterministic Template.
    """
    full_prompt = f"Topic: {topic}, Difficulty: {difficulty}. Generate 3 questions."

    try:
        data = await call_llm_api(OLLAMA_MODEL_NAME, full_prompt, timeout)
        quiz = Quiz.model_validate(data)
        logger.info("Successfully generated quiz using primary LLM: %s", OLLAMA_MODEL_NAME)
        return quiz

    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, ValidationError, json.JSONDecodeError) as e:
        logger.warning(
            "Primary LLM call failed or validation failed. Using deterministic fallback. Model attempted: %s", 
            OLLAMA_MODEL_NAME, 
            exc_info=True
        )
    
    logger.info("Falling back to deterministic quiz template.")
    return await deterministic_quiz_template(topic, difficulty)