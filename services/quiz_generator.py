import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

SYSTEM_PROMPT = """당신은 기독교 청년 소그룹의 주일 말씀(OBS)을 가볍게 되새기도록 돕는 복습 도우미입니다.
제공된 교안 내용을 바탕으로 (1) 그 주 말씀의 핵심 요약 3문장과 (2) 가볍게 복습할 퀴즈 3개(OX, 단답형, 짧은 서술형)를 생성하세요.

【목적 — 매우 중요】
- 이 퀴즈는 시험·평가가 아닙니다. 그 주 말씀의 핵심을 부담 없이 "기억나게" 하는 용도입니다.
- 본문을 한 번 듣고 읽은 사람이라면 잠깐 생각하면 자연스럽게 떠오르는 수준으로만 출제하세요.
- 어렵거나, 외워야 풀리거나, 성경 지식을 시험하는 문제는 실패입니다.

【모든 문제 공통 기준】
- 문제는 반드시 그 주 말씀의 "핵심 메시지와 삶의 적용"을 떠올리게 하는 것이어야 합니다.
- 질문만 읽어도 무엇을 묻는지 즉시 직관적으로 이해돼야 합니다. 쉬운 일상어로 쓰세요.
- 세 문제의 난이도를 비슷하게, 모두 가볍게 맞추세요.

【절대 출제 금지 (실제 나쁜 예시)】
1. 성경 이야기의 사건·인물·지명·숫자 등 서사/역사 디테일을 묻는 문제
   나쁜 예: "슬로브핫의 딸들이 결혼할 때, 요셉 지파 수령들은 그들의 땅이 다른 지파에게 넘어갈 것을 염려했습니다." (역사 사실 확인)
   - 교재가 예화로 든 성경 인물·이야기(야곱·나오미·탕자 등)도 그 줄거리/사건/결과를 묻지 마세요.
     나쁜 예: "야곱이 위기에서 밤새 기도했을 때 어떤 변화와 도움이 임했나요?" (예화 줄거리 확인)
     예화는 메시지를 떠올리는 보조일 뿐, 문제는 항상 그 주 핵심 메시지/주제 자체로 출제하세요.
2. 고유명사·지명·인물명·단어 암기가 정답인 단답형
   나쁜 예: 정답이 "지파"처럼 메시지와 무관한 본문 속 단어 하나를 맞히는 문제
3. 문제 안에 "○장 ○절" 같은 구절 번호 인용
   나쁜 예: "민수기 36장 10-12절 말씀처럼, 신앙 안에서 어떤 중요한 결과를…" → 구절 번호 없이 내용만으로 물으세요.
4. 모호하고 추상적인 질문 + 무엇이든 답이 되는 뜬구름 정답
   나쁜 예: Q "어떤 중요한 결과를 기대할 수 있습니까?" / A "은혜와 축복, 사명을 온전히 지키며…"
   → 무엇을 묻는지 분명하고, 정답도 한두 문장의 구체적이고 쉬운 말이어야 합니다.

【유형별 지침】
- 요약(summaries): 교안 내용에 근거한 3개의 완성된 문장. 괄호·빈칸 없이.
- 1번 OX: 그 주 메시지/적용의 핵심을 쉽게 확인하는 참/거짓. 정답은 반드시 "O" 또는 "X". (이야기 사실 확인 금지)
- 2번 단답형(SHORT): 정답은 그 주 메시지의 "핵심 개념어" 한 단어(예: 순종, 은혜). 막연·일반적인 단어(존중, 사랑 등 어느 설교에나 맞는 단어)와 인물·지명·고유명사는 금지.
    · 원칙 — 자연스러운 질문을 우선하세요. 질문을 읽으면 정답 단어가 자연스럽게 떠오르게 내고, 정답에 억지로 문제를 끼워맞추지 마세요. "~를 뜻하는 한 단어를 쓰세요" 같은 어색한 지시문 금지.
    · 예외(애매할 때만) — 정답이 자연스럽게 하나로 특정되지 않는 경우에는, 교재 본문의 실제 문장에서 그 단어 자리에 빈칸(______)을 만들어 문맥으로 답이 정해지게 하세요(빈칸 채우기). 빈칸은 기본이 아니라, 이렇게 애매한 경우에만 쓰는 방식입니다.
- 3번 짧은 서술형(ESSAY): 그 주 교재가 다룬 핵심 주제를 한 번 더 곱씹어 "생각해보게" 하는 질문. "내가 무엇을 다짐/적용하겠다" 같은 개인 결단형이 아니라, 교재 내용에 근거해 생각할 거리를 던지는 형식이어야 합니다.
    - 단, 너무 추상적·막연해 무엇이든 답이 되는 열린 질문은 금지. (나쁜 예: "신앙이란 무엇일까요?", "내가 적용하고 싶은 한 가지는?")
    - 좋은 예: "하나님께서 주신 은혜와 축복을 잘 지키기 위해 우리에게 필요한 것은 무엇일까요?" 처럼 교재가 답을 주는 구체적 주제.
    - correctAnswer는 교재가 말한 내용을 쉬운 말로 정리한 구체적 모범답안(null 금지) — 답을 보면 그 주 메시지가 떠오르게.

【해설(explanation)】
- 각 퀴즈에 짧고 직관적인 해설을 반드시 포함하세요. 읽으면 "아, 그렇지" 하고 그 주 메시지가 다시 떠오르게 하세요.

【인도자 해설 사용 금지】
- 인도자 해설(commentaries)은 참여자가 못 본 정보이므로 출제 재료로 쓰지 마세요. 성경 본문·말씀 제목·나눔 질문 등 공개된 내용에서만 출제하고, 인도자 해설은 explanation 작성 시 보충 맥락으로만 참고하세요.

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


def _flatten_tree_items(nodes: list, depth: int = 0) -> list[str]:
    lines: list[str] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue

        text = node.get("text", "")
        if text:
            prefix = "  " * depth
            number = node.get("number")
            lines.append(f"{prefix}- {number + ' ' if number else ''}{text}")

        for note in node.get("notes", []) or []:
            if note:
                prefix = "  " * (depth + 1)
                lines.append(f"{prefix}* NOTE: {note}")

        lines.extend(_flatten_tree_items(node.get("children", []) or [], depth + 1))
    return lines


def _build_point_summary(points: list) -> str:
    lines = []
    for i, p in enumerate(points):
        answer = p.get("answer") or "( )"
        title_filled = p.get("title", "").replace("( )", answer)
        
        q_lines = []
        items = p.get("items") or []
        if items and isinstance(items[0], dict) and "children" in items[0]:
            q_lines.extend([f"    {line}" for line in _flatten_tree_items(items)])
        else:
            for it in p.get("items") or p.get("questions") or []:
                it_text = it.get("text") if isinstance(it, dict) else it
                if it_text:
                    q_lines.append(f"    - {it_text}")
        
        # 라벨에 "포인트"라는 단어를 쓰지 않는다 — 모델이 그대로 베껴 출제 문구에 "포인트 N"이
        # 노출되던 문제(QA #26) 방지. reference(구절번호)는 정확도용 맥락으로만 두고,
        # 프롬프트에서 문제 안 인용을 금지한다.
        lines.append(
            f"[{p.get('number', i+1)}번 말씀] \"{answer}\" — {title_filled} ({p.get('reference', '')})\n"
            + "\n".join(q_lines)
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


def _build_material_context(sections: list) -> str:
    """sections를 [본문 배경]/[핵심 포인트]/[적용 질문] 블록 텍스트로 변환. 생성·재생성 공용."""
    intro = next((s for s in sections if s["type"] == "intro"), None)
    points = [s for s in sections if s["type"] == "point"]
    application = next((s for s in sections if s["type"] == "application"), None)

    # 적용 질문 텍스트 구성
    app_text = "없음"
    if application:
        app_items = application.get("items") or application.get("questions") or []
        if app_items and isinstance(app_items[0], dict) and "children" in app_items[0]:
            app_text = "\n".join(_flatten_tree_items(app_items))
        elif app_items:
            app_text = "\n".join([it.get("text", "") if isinstance(it, dict) else it for it in app_items])
        else:
            app_text = application.get("text", "없음") # 하위 호환성

    return f"""[본문 배경]
{intro["text"] if intro else "없음"}

[핵심 포인트]
{_build_point_summary(points)}

[적용 질문]
{app_text}"""


def generate_quizzes(sections: list) -> dict[str, list]:
    user_prompt = f"""다음은 OBS 말씀의 핵심 내용입니다.
이 내용을 바탕으로 다음 주 개인 복습용 퀴즈 3개를 생성해 주세요.

{_build_material_context(sections)}"""

    for attempt in range(2):
        try:
            response = model.generate_content(f"{SYSTEM_PROMPT}\n\n{user_prompt}")
            return json.loads(_clean_json_response(response.text))
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"퀴즈 생성 실패: {e}")

    return []


# 단계 → (questionType, 사람이 읽는 유형명). 재생성 시 유형은 이 단계에 고정된다.
_STEP_TYPES = {
    1: ("OX", "OX(참/거짓)"),
    2: ("SHORT", "단답형"),
    3: ("ESSAY", "짧은 서술형"),
}

# 유형별 포맷 잠금 문구 — SYSTEM_PROMPT가 3개 유형(OX 먼저)을 함께 설명해, 단건 재생성 시
# 엉뚱한 유형(예: 2번인데 OX 참/거짓 문장)이 새는 것을 첫 시도부터 막는다.
_TYPE_LOCKS = {
    "OX": '이 문제는 참/거짓을 묻는 OX 문장이어야 하며, correctAnswer는 정확히 "O" 또는 "X"여야 합니다.',
    "SHORT": (
        "이 문제는 단답형입니다. 절대 참/거짓(OX) 문장으로 만들지 마세요. "
        'correctAnswer는 "O"/"X"가 아니라 낱말 하나여야 합니다. '
        "자연스러운 질문을 우선하되(정답에 억지로 끼워맞추지 말 것, '~를 뜻하는 한 단어를 쓰세요' 금지), "
        "정답이 자연스럽게 특정되지 않는 애매한 경우에만 교재 본문 문장에 빈칸(______)을 만들어 채우게 하세요."
    ),
    "ESSAY": "이 문제는 짧은 서술형입니다. OX·단답이 아니라 한두 문장으로 생각을 정리하게 하고, correctAnswer는 모범답안 문장입니다.",
}


def _validate_quiz_type(quiz: dict, q_type: str) -> bool:
    """생성 결과가 기대 유형과 실제로 맞는지(라벨이 아니라 내용/정답 기준) 검증."""
    ans = (quiz.get("correctAnswer") or "").strip()
    question = (quiz.get("questionText") or "").strip()
    if not question:
        return False
    upper = ans.upper()
    if q_type == "OX":
        return upper in ("O", "X")
    if q_type == "SHORT":
        # 단답형인데 정답이 O/X면 실제로는 OX형이 샌 것 → 거부
        return bool(ans) and upper not in ("O", "X")
    if q_type == "ESSAY":
        return bool(ans)
    return True


def regenerate_single_quiz(
    sections: list,
    step_number: int,
    current_question: str | None = None,
    instruction: str | None = None,
    other_questions: list[str] | None = None,
) -> dict:
    """검수 화면에서 특정 문제 1개만 다시 생성한다. 유형(step)은 고정, 나머지 문제와 중복 회피,
    관리자가 적은 지침(instruction)을 함께 반영한다. 생성 결과가 기대 유형과 맞는지 검증하고
    맞을 때까지 재시도(최대 3회) — 끝내 실패하면 예외. 퀴즈 dict 1개를 반환."""
    if step_number not in _STEP_TYPES:
        raise ValueError(f"invalid step_number: {step_number}")
    q_type, type_label = _STEP_TYPES[step_number]

    avoid_lines = []
    if current_question:
        avoid_lines.append(f'- 지금 문제(같은 걸 다시 내지 말고 새롭게): "{current_question}"')
    for oq in other_questions or []:
        if oq:
            avoid_lines.append(f'- 다른 문제와 겹치지 마세요: "{oq}"')
    avoid_block = ("\n".join(avoid_lines)) if avoid_lines else "- (없음)"

    instruction_block = (
        f"\n[관리자 요청 — 반드시 반영]\n{instruction.strip()}"
        if instruction and instruction.strip()
        else ""
    )

    user_prompt = f"""다음은 OBS 말씀의 핵심 내용입니다.
아래 기준(위 시스템 지침)을 그대로 지키되, **{step_number}번 문제({type_label})만 1개** 새로 만들어 주세요.
questionType은 반드시 "{q_type}"이어야 합니다.

[유형 규칙 — 반드시 준수]
{_TYPE_LOCKS[q_type]}

{_build_material_context(sections)}

[피해야 할 문제]
{avoid_block}{instruction_block}

출력은 아래 JSON "하나만" 반환하세요(설명·추가 텍스트 없이):
{{"stepNumber": {step_number}, "questionType": "{q_type}", "questionText": "...", "correctAnswer": "...", "explanation": "..."}}"""

    last_err = None
    for attempt in range(3):
        try:
            response = model.generate_content(f"{SYSTEM_PROMPT}\n\n{user_prompt}")
            data = json.loads(_clean_json_response(response.text))
            # 모델이 배열/래핑으로 줄 수 있으니 방어적으로 단일 dict로 정규화
            if isinstance(data, dict) and "quizzes" in data and data["quizzes"]:
                data = data["quizzes"][0]
            if isinstance(data, list):
                data = data[0]
            data["stepNumber"] = step_number
            data["questionType"] = q_type  # 유형 라벨은 코드가 고정
            # 라벨만 고정하면 'OX 내용 + SHORT 라벨'이 새므로, 내용/정답으로 유형을 검증
            if _validate_quiz_type(data, q_type):
                return data
            last_err = RuntimeError(
                f"유형 불일치(기대 {q_type}, 정답={data.get('correctAnswer')!r})"
            )
        except Exception as e:
            last_err = e

    raise RuntimeError(f"문제 재생성 실패: {last_err}")
