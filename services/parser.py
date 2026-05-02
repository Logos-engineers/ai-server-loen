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
1. type=intro: 교재의 시작 부분(III. 말씀 정리하기)부터 본격적인 1번 질문이 나오기 전까지의 도입부입니다.
   - text: 텍스트 박스 안의 도입 단락 전체.
   - items: 도입 직후에 나오는 배경 설명이나 첫 번째 질문 전의 가벼운 준비 질문들.

2. type=point: "1. ", "2. ", "3. " 등 대문항 번호로 시작하는 학습 질문 블록입니다.
   - 각 대문항(1., 2. ...)마다 하나의 point 섹션을 생성합니다.
   - title: 대문항의 질문 제목 (빈칸은 ( )로 유지).
   - answer: ( ) 안의 정답 단어 (없으면 null).
   - items: 해당 대문항 아래의 모든 세부 항목을 반드시 이 배열에 넣습니다. (필드명은 반드시 'items'여야 합니다)
     * level 1: 중문항 ((1), (2) 등)
     * level 2: 소문항 (1), 2) 등)
     * level 3: 더 세부적인 항목 (- 등)
     * NOTE: ▶ 기호로 시작하는 해설 (parent 항목 직후에 배치)

3. type=application: 교재 마지막의 "IV. 적용하기" 이후 또는 번호가 다시 1번부터 리셋되는 구간입니다.
   - items: 삶에의 적용, 개인 묵상 질문들.

=== items 배열 내 항목(item) 스키마 ===
각 항목은 반드시 다음 필드를 포함해야 합니다:
- role: 'QUESTION', 'SUB_QUESTION', 'ANSWER_DETAIL', 'NOTE' 중 하나.
- level: 정수 (1, 2, 3).
- text: 정제된 텍스트.

=== 텍스트 정제 규칙 ===
- 문장 시작의 기호("1.", "(1)", "1)", "-", "•", "▶")만 제거.
- "2025년", "3가지" 등 본문 내의 숫자/연도는 절대 제거하지 마세요.

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
