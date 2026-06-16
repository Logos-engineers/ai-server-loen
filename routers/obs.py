from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import os
import re
import traceback
import sys
from services.pdf_extractor import extract_text_from_r2
from services.parser import parse_obs_sections
from services.quiz_generator import generate_quizzes

router = APIRouter()

# 내부 전용 서비스 — 백엔드 중계만 호출하도록 공유 시크릿으로 보호한다.
# 미설정 시(운영 오설정) 열려버리지 않도록 호출을 거부(fail-closed)한다.
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN")

# 허용 R2 키 패턴 — obs/ 접두사 + 단일 세그먼트 + .pdf. 경로 탈출/임의 객체 열람 차단.
_R2_KEY_PATTERN = re.compile(r"^obs/[A-Za-z0-9._-]+\.pdf$")


def verify_internal_token(x_internal_token: str | None):
    if not INTERNAL_API_TOKEN:
        # 토큰 미설정이면 안전하게 거부 (백엔드·AI 양쪽에 동일 INTERNAL_API_TOKEN 필요)
        raise HTTPException(status_code=503, detail="service_unconfigured")
    if x_internal_token != INTERNAL_API_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class ProcessRequest(BaseModel):
    r2_key: str


class ProcessResponse(BaseModel):
    sections: list
    summary: list[str]
    quizzes: list


@router.post("/process", response_model=ProcessResponse)
def process_obs(request: ProcessRequest, x_internal_token: str | None = Header(default=None)):
    verify_internal_token(x_internal_token)

    # r2_key 검증 — 허용 패턴 외(임의 버킷 객체)면 거부
    if not _R2_KEY_PATTERN.match(request.r2_key):
        raise HTTPException(status_code=400, detail="invalid_r2_key")

    try:
        print(f"[AI] Processing R2 Key: {request.r2_key}", file=sys.stderr)
        pdf_text = extract_text_from_r2(request.r2_key)

        print(f"[AI] Extracted text length: {len(pdf_text)}", file=sys.stderr)
        sections = parse_obs_sections(pdf_text)

        print(f"[AI] Parsed sections count: {len(sections)}", file=sys.stderr)

        # generate_quizzes 결과가 dict인지 list인지에 따라 처리
        ai_result = generate_quizzes(sections)

        if isinstance(ai_result, dict):
            quizzes = ai_result.get("quizzes", [])
            summary = ai_result.get("summaries", [])
        else:
            # 리스트로 왔을 경우 (이전 버전 호환성)
            quizzes = ai_result
            summary = []

        print(f"[AI] Generated summaries: {len(summary)}, quizzes: {len(quizzes)}", file=sys.stderr)

        return ProcessResponse(sections=sections, summary=summary, quizzes=quizzes)
    except HTTPException:
        raise
    except Exception as e:
        # 내부 오류 원문은 서버 로그에만 남기고, 신뢰 경계 밖(응답)으로는 일반 메시지만 반환
        print(f"[AI] ERROR: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="processing_failed")
