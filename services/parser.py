import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

SYSTEM_PROMPT = """당신은 기독교 청년회 OBS(말씀 공부) 교재를 구조화하는 도우미입니다.
제공된 PDF 텍스트에서 아래 JSON 스키마에 맞게 섹션을 추출하세요.

규칙:
1. type=intro: III. 말씀 정리하기 박스(도입 단락)
   - text: 박스 안 도입 본문 단락 전체
   - questions: 도입 단락 이후 "1." "2." 등으로 시작하는 전체 본문 대상 나눔 질문 전체 목록
     (포인트 진입 전 맥락을 잡는 전환 질문도 포함, 1개 이상 가변)
   - commentaries: questions 배열과 같은 순서/길이로, 각 질문 바로 아래
     "▶"로 시작하는 인도자 해설. 해당 질문에 ▶가 없으면 null

2. type=point: 핵심 포인트 (1)(2)(3)... 소제목, 성경 참조, 나눔 질문 목록 — 개수는 2개 이상 가변
   - number: 포인트 번호 (정수)
   - title: 빈칸을 ( )로 유지 (예: "( ) 절기를 지키는 법칙입니다.")
   - answer: 인도자용 PDF의 경우 ( ) 안 채워진 정답 단어, 교재용이면 null
   - reference: 해당 포인트 성경 참조
   - questions: 포인트 아래 "1)" 형식 나눔 질문 목록
   - commentaries: questions 배열과 같은 순서/길이로, 각 질문 바로 아래
     "▶"로 시작하는 인도자 해설. 해당 질문에 ▶가 없으면 null

3. type=application: IV. 적용하기 질문 문장
   - text: 적용 질문 전체

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
