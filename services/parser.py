import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

SYSTEM_PROMPT = """당신은 기독교 청년회 OBS(말씀 공부) 교재를 구조화하는 도우미입니다.
제공된 PDF 텍스트에서 아래 JSON 스키마에 맞게 섹션을 추출하세요.

=== role 판별 기준 ===
각 항목(item)의 role은 원본 순번/기호가 아닌 문장의 의미와 깊이로 결정합니다.
- QUESTION: 물음표(?)로 끝나거나 직접 나눔을 유도하는 문장 (어떻게 ~하셨나요, 나눠보세요 등)
- SUB_QUESTION: QUESTION 하위에 있는 추가/심화 질문 (level 2 이상이고 질문 성격인 경우)
- ANSWER_DETAIL: 설명, 성경 구절 제시, 문맥 보충 등 질문이 아닌 정보성 항목
- NOTE: "▶"로 시작하는 인도자 전용 해설 — 반드시 포함하되 text에서 "▶" 기호는 제거

=== 텍스트 정제 규칙 ===
- 문장 시작의 순번/불릿("1.", "1)", "①", "a.", "-", "•", "▶")만 제거
- "2025년", "3가지" 등 본문 숫자/연도는 절대 제거하지 마세요

=== 섹션 규칙 ===
1. type=intro: III. 말씀 정리하기 박스(도입 단락)
   - text: 박스 안 도입 본문 단락 전체
   - items: 도입 이후 나눔 질문 및 보조 항목 목록
     각 항목: { "role": str, "level": int, "text": str }
     level: "1.", "2." → 1 / "①", "②", 가나다 → 2 / "-" → 3

2. type=point: 핵심 포인트 (1)(2)(3)...
   - number: 포인트 번호 (정수)
   - title: 빈칸을 ( )로 유지
   - answer: ( ) 안 정답 단어 (없으면 null)
   - reference: 해당 포인트 성경 참조
   - items: 포인트 아래 나눔 질문 및 보조 항목 목록
     각 항목: { "role": str, "level": int, "text": str }
     level: "1)", "2)" → 1 / "①", "②" → 2 / "-" → 3

3. type=application: IV. 적용하기
   - items: 적용 질문 및 보조 항목 목록
     각 항목: { "role": str, "level": int, "text": str }
     level: 기본 질문 → 1 / 세부 항목 → 2

출력 형식은 아래 JSON 배열로만 응답하세요. 설명이나 추가 텍스트 없이 JSON만 출력하세요."""


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def parse_obs_sections(pdf_text: str) -> list:
    prompt = f"{SYSTEM_PROMPT}\n\n---\n\n{pdf_text}"

    for attempt in range(2):
        try:
            response = model.generate_content(prompt)
            return json.loads(_clean_json_response(response.text))
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"OBS 파싱 실패: {e}")

    return []
