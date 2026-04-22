import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

SYSTEM_PROMPT = """당신은 기독교 청년회 소그룹 말씀 공부(OBS)를 돕는 도우미입니다.
제공된 설교 내용과 핵심 포인트를 바탕으로, 소그룹 복습에 적합한 퀴즈 3개를 생성하세요.

각 퀴즈는 문제, 정답뿐만 아니라 학습을 돕기 위한 **짧고 명확한 해설(explanation)**을 반드시 포함해야 합니다.

규칙:
1. OX 문제(1번): 인도자 해설에 등장하는 사실 관계나 성경 사례를 활용해 출제. 정답은 반드시 "O" 또는 "X"
2. 단답형 문제(2번): 각 포인트의 핵심 키워드(answer)나 본문에서 직접 찾을 수 있는 단어로 정답 설정. 정답은 5~15자 내외
3. 서술형 문제(3번): 적용 질문 맥락과 연결된 삶의 적용 열린 질문. 정답 없음(null)

출력 형식은 반드시 아래 JSON 배열 구조로만 응답하세요. 설명이나 추가 텍스트 없이 JSON만 출력하세요.

JSON 구조 예시:
[
  {
    "stepNumber": 1,
    "questionType": "OX",
    "questionText": "문제 내용...",
    "correctAnswer": "O",
    "explanation": "해당 정답의 근거가 되는 성경적 배경이나 해설..."
  },
  {
    "stepNumber": 2,
    "questionType": "SHORT",
    "questionText": "문제 내용...",
    "correctAnswer": "정답단어",
    "explanation": "이 단어가 핵심인 이유와 본문의 맥락 설명..."
  },
  {
    "stepNumber": 3,
    "questionType": "ESSAY",
    "questionText": "적용 질문 내용...",
    "correctAnswer": null,
    "explanation": "이 질문을 통해 묵상해볼 점이나 인도자 가이드..."
  }
]"""


def _build_point_summary(points: list) -> str:
    lines = []
    for p in points:
        answer = p.get("answer") or "( )"
        title_filled = p.get("title", "").replace("( )", answer)
        commentary = (p.get("commentaries") or [None])[0] or "없음"
        lines.append(
            f"포인트 {p['number']}. \"{answer}\" — {title_filled} ({p.get('reference', '')})\n"
            f"  인도자 해설: {commentary}"
        )
    return "\n".join(lines)


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def generate_quizzes(sections: list) -> list:
    intro = next((s for s in sections if s["type"] == "intro"), None)
    points = [s for s in sections if s["type"] == "point"]
    application = next((s for s in sections if s["type"] == "application"), None)

    user_prompt = f"""다음은 OBS 말씀의 핵심 내용입니다.
이 내용을 바탕으로 다음 주 개인 복습용 퀴즈 3개를 생성해 주세요.

[본문 배경]
{intro["text"] if intro else "없음"}

[핵심 포인트]
{_build_point_summary(points)}

[적용 질문]
{application["text"] if application else "없음"}"""

    for attempt in range(2):
        try:
            response = model.generate_content(f"{SYSTEM_PROMPT}\n\n{user_prompt}")
            return json.loads(_clean_json_response(response.text))
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"퀴즈 생성 실패: {e}")

    return []
