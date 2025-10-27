# In app/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional

class Question(BaseModel):
    id: str = Field(..., description="unique id for question")
    # >>>>> Field name is 'question_text' <<<<<
    question_text: str 
    # >>>>> Field name is 'options' <<<<<
    options: List[str] = Field(..., min_items=4, max_items=4) 
    # >>>>> Field name is 'correct_answer_index' <<<<<
    correct_answer_index: int = Field(..., ge=0, le=3) 
    explanation: Optional[str] = None
    metadata: Optional[dict] = {}

class Quiz(BaseModel):
    quiz_id: str
    topic: str
    difficulty: str
    questions: List[Question]
    time_limit_seconds: Optional[int] = 600
    created_by: Optional[str] = None
# ... other schemas ...