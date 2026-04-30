import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

SYSTEM_PROMPT = """당신은 기독교 청년회 소그룹 말씀 공부(OBS)를 돕는 도우미입니다.
제공된 설교 내용과 핵심 포인트를 바탕으로 다음 두 가지를 생성하세요:
1. 이번 주 말씀의 가장 핵심적인 메시지 3가지 요약 (반드시 제공된 교재 텍스트 내용으로만 작성할 것)
2. 소그룹 복습에 적합한 퀴즈 3개 (OX, 단답형, 서술형)

규칙:
- 요약(summaries): 교안 텍스트에 근거하여 3개의 문장으로 작성하세요. 괄호나 빈칸이 없는 완성된 문장이어야 합니다.
- 퀴즈(quizzes):
    1. OX 문제(1번): 성경 본문과 포인트의 핵심 내용을 활용해 출제. 정답은 반드시 "O" 또는 "X"
    2. 단답형 문제(2번): 포인트의 핵심 키워드를 정답으로 설정.
    3. 서술형 문제(3번): 열린 나눔 질문이 아니라, 본문이 말하는 의미/결과/경고/바른 반응을 짧게 답할 수 있는 문제로 출제. 정답은 null이 아니라 1~2문장의 짧은 모범답안으로 작성.

- 인도자 해설(commentaries)은 절대 문제의 출제 재료로 사용하지 마세요.
    - 인도자 해설은 인도자 전용 가이드이므로, 참여자가 직접 접근할 수 없는 정보입니다.
    - 퀴즈 문제와 정답은 반드시 성경 본문, 포인트 제목, 나눔 질문 등 교안의 공개된 내용에서만 출제하세요.
    - 인도자 해설은 explanation(해설) 작성 시 보충 맥락으로만 참고할 수 있습니다.

- 모든 questionText는 짧고 바로 이해 가능해야 합니다.
    - 가능하면 1문장으로 작성하고, 불필요한 배경 설명 없이 핵심만 물어보세요.
    - "OBS 자료에서", "포인트 1에서", "본문을 보면", "다음을 통해", "어떤 내용을 확인했을 때" 같은 메타 표현은 사용하지 마세요.
    - 질문만 읽어도 바로 의미가 전달되도록 핵심 주어와 개념을 직접 넣으세요.
    - 너무 길게 쓰지 말고, 읽기 쉬운 짧은 문장으로 작성하세요.

- 단답형(2번) 문제는 다음 기준을 반드시 지키세요.
    - 질문을 읽었을 때 정답이 단어 1~3개짜리 명사/형용사라는 것을 자연스럽게 알 수 있어야 합니다.
      좋은 예: "발락의 사신들은 어떤 사람들로 구성되어 있었습니까?" → 정답: "유력한 자들"
      나쁜 예: "발락이 이용했던 사람들은 어떤 특징이 있었습니까?" (주어가 모호하고 답의 형태를 유추하기 어려움)
    - 주어(누가/무엇이)를 질문 안에 명확히 밝히세요. "사람들", "그들" 같은 대명사만으로는 부족합니다.
    - 단어 암기 수준의 vocabulary recall이 아니라, 포인트의 핵심 개념이나 신학적 의미를 묻는 질문을 만드세요.
      피해야 할 패턴: 본문에 등장하는 형용사 한 단어를 그대로 맞추는 문제
      권장 패턴: "~가 ~한 이유는 무엇입니까?", "~의 결과로 ~은 어떻게 되었습니까?"

- 3번 서술형은 다음 기준을 반드시 지키세요.
    - "나누어 봅시다", "생각해 봅시다", "어떻게 느끼나요" 같은 열린 질문 표현은 금지합니다.
    - 사용자가 답을 적은 뒤 정답 보기에서 내용을 다시 복습할 수 있어야 합니다.
    - correctAnswer에는 짧은 모범답안을, explanation에는 그 답의 근거를 짧게 보충하세요.

- 각 퀴즈는 짧고 명확한 해설(explanation)을 반드시 포함해야 합니다.

출력 형식은 반드시 아래 JSON 구조로만 응답하세요. 설명이나 추가 텍스트 없이 JSON만 출력하세요.

JSON 구조 예시:
{
  "summaries": [
    "첫 번째 핵심 요약 문장...",
    "두 번째 핵심 요약 문장...",
    "세 번째 핵심 요약 문장..."
  ],
  "quizzes": [
    {
      "stepNumber": 1,
      "questionType": "OX",
      "questionText": "문제 내용...",
      "correctAnswer": "O",
      "explanation": "해설 내용..."
    },
    {
      "stepNumber": 2,
      "questionType": "SHORT",
      "questionText": "문제 내용...",
      "correctAnswer": "정답",
      "explanation": "해설 내용..."
    },
    {
      "stepNumber": 3,
      "questionType": "ESSAY",
      "questionText": "삶과 믿음에 어떤 영향이 생기나요?",
      "correctAnswer": "은혜 받는 길이 막히고 죄의 열매를 맺게 되어 믿음이 무뎌집니다.",
      "explanation": "가이드 내용..."
    }
  ]
}"""


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


def generate_quizzes(sections: list) -> dict[str, list]:
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
