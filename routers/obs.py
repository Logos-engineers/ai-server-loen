from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.pdf_extractor import extract_text_from_r2
from services.parser import parse_obs_sections
from services.quiz_generator import generate_quizzes

router = APIRouter()


class ProcessRequest(BaseModel):
    r2_key: str


class ProcessResponse(BaseModel):
    sections: list
    quizzes: list


@router.post("/process", response_model=ProcessResponse)
def process_obs(request: ProcessRequest):
    try:
        pdf_text = extract_text_from_r2(request.r2_key)
        sections = parse_obs_sections(pdf_text)
        quizzes = generate_quizzes(sections)
        return ProcessResponse(sections=sections, quizzes=quizzes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
