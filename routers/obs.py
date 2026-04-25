from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import traceback
import sys
from services.pdf_extractor import extract_text_from_r2
from services.parser import parse_obs_sections
from services.quiz_generator import generate_quizzes

router = APIRouter()

# ... (중략) ...

@router.post("/process", response_model=ProcessResponse)
def process_obs(request: ProcessRequest):
    try:
        print(f"[AI] Processing R2 Key: {request.r2_key}", file=sys.stderr)
        pdf_text = extract_text_from_r2(request.r2_key)
        
        print(f"[AI] Extracted text length: {len(pdf_text)}", file=sys.stderr)
        sections = parse_obs_sections(pdf_text)
        
        print(f"[AI] Parsed sections count: {len(sections)}", file=sys.stderr)
        quizzes = generate_quizzes(sections)
        
        print(f"[AI] Generated quizzes count: {len(quizzes)}", file=sys.stderr)
        return ProcessResponse(sections=sections, quizzes=quizzes)
    except Exception as e:
        print(f"[AI] ERROR: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
