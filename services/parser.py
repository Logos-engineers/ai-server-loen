import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

SYSTEM_PROMPT = """당신은 기독교 청년회 OBS(말씀 공부) 교재를 구조화하는 도우미입니다.
제공된 PDF 텍스트에서 아래 JSON 스키마에 맞게 섹션을 추출하세요.

규칙:
1. type=intro: III. 말씀 정리하기 박스(도입 단락)
   - text: 박스 안 도입 본문 단락 전체
   - questions: 도입 단락 이후 나눔 질문 및 보조 설명 목록.
     **중요:** 
     - "▶"로 시작하는 인도자용 설명/해설은 절대 포함하지 마세요.
     - **텍스트 정제:** 문장 시작의 "1.", "1)", "①", "a.", "-", "•" 등 **순번이나 불렛 기호만** 제거하세요.
     - **주의:** "2025년", "3가지" 등 본문 내용에 해당하는 숫자나 연도는 절대 제거하지 말고 그대로 유지하세요.
     - 각 항목은 객체 { "text": str, "level": int } 형식입니다.
     - level: "1.", "2." 는 1 / "①", "②" 혹은 가나다 등은 2 / "-" 는 3

2. type=point: 핵심 포인트 (1)(2)(3)... 소제목, 성경 참조, 나눔 질문 목록
   - number: 포인트 번호 (정수)
   - title: 빈칸을 ( )로 유지
   - answer: ( ) 안 채워진 정답 단어
   - reference: 해당 포인트 성경 참조
   - questions: 포인트 아래 나눔 질문 및 보조 설명 목록.
     **중요:** 
     - "▶"로 시작하는 인도자용 설명/해설은 절대 포함하지 마세요.
     - **텍스트 정제:** 문장 시작의 "1.", "1)", "①", "a.", "-", "•" 등 **순번이나 불렛 기호만** 제거하세요.
     - **주의:** "2025년", "3가지" 등 본문 내용에 해당하는 숫자나 연도는 절대 제거하지 말고 그대로 유지하세요.
     - 각 항목은 객체 { "text": str, "level": int } 형식입니다.
     - level: "1)", "2)" 등 숫자는 1 / "①", "②" 등 원문자는 2 / "-" 는 3

3. type=application: IV. 적용하기 질문 문장들
   - questions: 적용 질문 목록.
     **중요:** 
     - **텍스트 정제:** 문장 시작의 "1.", "1)", "①", "a.", "-", "•" 등 **순번이나 불렛 기호만** 제거하세요.
     - 각 항목은 객체 { "text": str, "level": int } 형식입니다.
     - level: 기본 질문은 1 / 세부 항목이나 보조 질문은 2

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
