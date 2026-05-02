import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

SYSTEM_PROMPT = """당신은 기독교 청년회 OBS(말씀 공부) 교재를 구조화하는 도우미입니다.
제공된 PDF 텍스트에서 아래 JSON 스키마에 맞게 섹션을 추출하세요.

=== 섹션 구분 원칙 (중요) ===
1. type=intro: 교재의 시작 부분부터 본격적인 1번 질문이 나오기 전까지의 도입부만 포함합니다.
   - 텍스트 박스 안의 도입 단락은 intro의 'text'에 넣습니다.
   - 도입 직후에 나오는 배경 설명이나 준비 질문은 intro의 'items'에 넣습니다.

2. type=point: "1. ", "2. ", "3. " 등 큰 번호로 시작하는 핵심 질문부터는 반드시 새로운 point 섹션으로 분리합니다.
   - **절대로 모든 질문을 intro에 몰아넣지 마세요.** 각 큰 번호(1, 2, 3...)가 하나의 point 섹션이 됩니다.
   - number: 포인트 번호 (1, 2, 3...)
   - title: 포인트의 큰 질문 또는 핵심 요약 문구 (빈칸은 ( )로 유지)
   - answer: ( ) 안 정답 단어 (없으면 null)
   - reference: 해당 포인트의 성경 참조
   - items: 해당 포인트 아래의 모든 세부 질문(1), 2), ①, ② 등)과 인도자 해설(▶)

3. type=application: 교재 마지막의 "IV. 적용하기" 이후 내용을 포함합니다.

=== role 판별 기준 ===
- QUESTION: 물음표(?)로 끝나거나 직접 나눔을 유도하는 문장
- SUB_QUESTION: QUESTION 하위에 있는 추가/심화 질문
- ANSWER_DETAIL: 설명, 성경 구절 제시, 문맥 보충 등 정보성 항목
- NOTE: "▶"로 시작하는 인도자 전용 해설 (text에서 "▶" 기호 제거)

=== 텍스트 정제 규칙 ===
- 문장 시작의 순번/불릿("1.", "1)", "①", "a.", "-", "•", "▶")만 제거
- "2025년", "3가지" 등 본문 숫자/연도는 절대 제거하지 마세요

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
