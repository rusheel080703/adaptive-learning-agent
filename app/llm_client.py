# app/llm_client.py
import uuid
import logging
import json
from typing import Any, List # Added List for clarity
from app.schemas import Quiz # Assumes Quiz is imported from your schemas file
import httpx
import os
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Read variables from environment, ensuring defaults are correct for Docker
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL_NAME = os.environ.get("OLLAMA_MODEL_NAME", "mistral:7b")
# You can define a fallback model if needed, but the template is the ultimate fallback
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL_NAME", "llama3:latest") # Example

# In app/llm_client.py

async def deterministic_quiz_template(topic: str, difficulty: str) -> Quiz:
    """Simple deterministic fallback that creates a 3-question quiz."""
    qid = str(uuid.uuid4())
    questions_data = [] # Use a temporary list for raw data
    for i in range(3):
        questions_data.append({
            "id": f"{qid}-{i}",
            # FIX: Use the EXACT field name from schemas.py
            "question_text": f"Sample {difficulty} question {i+1} about {topic}", 
            # FIX: Use the EXACT field name from schemas.py
            "options": ["A", "B", "C", "D"], 
            # FIX: Use the EXACT field name from schemas.py and ensure it's an int
            "correct_answer_index": 0, 
            "explanation": f"Explanation for question {i+1}"
            # Ensure 'metadata' is handled if present in your Question schema
            # "metadata": {} # Add if needed
        })
    
    # Validate the generated list of dicts against the Question schema implicitly
    # when creating the Quiz object.
    try:
        # Pass the correctly keyed data directly to the Quiz constructor
        quiz_obj = Quiz(
            quiz_id=qid,
            topic=topic,
            difficulty=difficulty,
            questions=questions_data 
        )
        return quiz_obj
    except ValidationError as e:
        logger.error("Pydantic validation failed INSIDE deterministic template!", exc_info=True)
        # If this fails, something is fundamentally wrong with schema/data shapes
        # For robustness, return a minimal, guaranteed valid Quiz
        return Quiz(quiz_id=str(uuid.uuid4()), topic="Error", difficulty="error", questions=[])

# ... (rest of the file remains the same) ...

async def call_llm_api(model_name: str, prompt: str, timeout: int) -> dict:
    """Handles the actual API call to the Ollama endpoint."""
    url = f"{OLLAMA_URL}/api/generate"

    # Define the expected JSON structure clearly in the prompt
    # Adjust the keys (e.g., 'question_text', 'correct_answer_index') 
    # to EXACTLY match your Pydantic schema.py model definitions.
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
          "explanation": "string (optional explanation)"
        }}
        // ... more questions ...
      ]
    }}
    Do NOT include any preamble, commentary, markdown fences (```json), or any text outside the main JSON object.
    The quiz must contain exactly 3 questions about the topic: {prompt}.
    """

    payload = {
        "model": model_name,
        # Send only the user request, let the system prompt handle structure
        "prompt": f"User Request: {prompt}", 
        "system": system_prompt, # Use Ollama's system prompt field if available/needed
        "stream": False,
        "format": "json" # Crucial for Ollama structured output
    }

    logger.info("Attempting LLM call to %s with model %s", url, model_name)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status() # Raises HTTPStatusError for 4xx/5xx responses
        raw_response = resp.json()

        # Try to parse the nested JSON string from Ollama's 'response' field
        try:
            json_str = raw_response.get("response", "{}") # Default to empty JSON string if 'response' is missing
            if isinstance(json_str, str):
                # Clean potential markdown fences (though format=json should prevent this)
                cleaned_json_str = json_str.strip().strip('```json').strip('```')
                # Load the cleaned string into a Python dict
                data = json.loads(cleaned_json_str) 
                return data
            elif isinstance(json_str, dict):
                 # If 'response' field is already a dict (less common for /generate)
                 return json_str
            else:
                 # If the main response is the JSON (less common)
                 return raw_response
                 
        except json.JSONDecodeError as json_err:
            logger.error("Failed to decode JSON from LLM response string: %s", json_str, exc_info=True)
            raise ValueError(f"Invalid JSON output structure from LLM: {json_err}") from json_err
        except Exception as e:
             logger.error("Unexpected error parsing LLM response.", exc_info=True)
             raise ValueError("Unexpected error processing LLM output.") from e


async def call_ollama_or_fallback(topic: str, difficulty: str, timeout: int = 30) -> Quiz: # Increased timeout
    """
    Tries primary LLM (Mistral), logs detailed errors, then uses Deterministic Template.
    """
    full_prompt = f"Topic: {topic}, Difficulty: {difficulty}. Generate 3 questions."

    # 1. PRIMARY ATTEMPT (Mistral/Ollama)
    try:
        data = await call_llm_api(OLLAMA_MODEL_NAME, full_prompt, timeout)

        # Use Pydantic V2 model validation
        quiz = Quiz.model_validate(data) # Updated from parse_obj
        logger.info("Successfully generated quiz using primary LLM: %s", OLLAMA_MODEL_NAME)
        return quiz

    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, ValidationError, json.JSONDecodeError) as e:
        # Log the full traceback for detailed debugging
        logger.warning(
            "Primary LLM call failed or validation failed. Using deterministic fallback. Model attempted: %s", 
            OLLAMA_MODEL_NAME, 
            exc_info=True # This adds the full exception traceback to the log
        )
        # No need for FALLBACK_MODEL logic if the ultimate fallback is the template

    # 3. DETERMINISTIC TEMPLATE (100% guarantee)
    logger.info("Falling back to deterministic quiz template.")
    return await deterministic_quiz_template(topic, difficulty)