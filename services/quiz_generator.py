import google.generativeai as genai
import anthropic
import json
import os
import re
import sys
from dotenv import load_dotenv

load_dotenv()

# 공급자: Claude 기본 → 실패 시 Gemini 폴백. 8개 교안 × 5개 모델 비교에서 Opus 5만 OX 정답 편향
# (Gemini 2.5-flash는 O 7/8)이 해소됐다. docs/obs-quiz-model-comparison.html
# QUIZ_PROVIDER=gemini 이거나 ANTHROPIC_API_KEY가 없으면 Gemini만 쓴다(키 넣기 전 배포해도 기존과 동일).
CLAUDE_MODEL = "claude-opus-5"
# 2.5 계열은 지원 종료 신호(2.5-pro가 이미 신규 사용자 404) → 버전 고정 가능한 최신 flash로.
GEMINI_MODEL = "gemini-3.8-flash"

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
_gemini = genai.GenerativeModel(GEMINI_MODEL)
_claude: anthropic.Anthropic | None = None  # 키 없는 환경(CI import 스모크 등)에서 import가 깨지지 않게 지연 생성


def _providers() -> list[str]:
    if os.getenv("QUIZ_PROVIDER", "claude").strip().lower() == "claude" and os.getenv("ANTHROPIC_API_KEY"):
        return ["claude", "gemini"]
    return ["gemini"]


def _complete(provider: str, prompt: str) -> str:
    global _claude
    if provider == "gemini":
        return _gemini.generate_content(prompt).text
    if _claude is None:
        _claude = anthropic.Anthropic(timeout=120.0)  # SDK가 429/5xx/연결 오류를 2회 자동 재시도
    # 서버 측 폴백: 안전 분류기가 거절하면 같은 요청을 다른 Claude 모델로 재실행(분류별 자동 라우팅).
    response = _claude.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("claude refusal")
    return "".join(b.text for b in response.content if b.type == "text")


def _generate(prompt: str, parse, attempts: int) -> tuple[object, str]:
    """공급자 순서대로 시도한다. parse가 예외를 던지면(JSON 깨짐·유형 불일치) 같은 공급자로
    attempts회까지 재시도, 그래도 실패하거나 API 오류(크레딧 소진·인증·거절 포함)면 다음 공급자로.
    반환: (parse 결과, 실제로 생성한 모델명)."""
    last_err: Exception | None = None
    for provider in _providers():
        model_name = CLAUDE_MODEL if provider == "claude" else GEMINI_MODEL
        for _ in range(attempts):
            try:
                return parse(_complete(provider, prompt)), model_name
            except anthropic.APIError as e:
                last_err = e
                print(f"[AI] {model_name} API 오류({type(e).__name__}) → 다음 공급자", file=sys.stderr)
                break  # 크레딧·인증(4xx)·SDK 재시도까지 소진한 5xx/연결 오류는 같은 공급자로 반복해도 소용없다
            except Exception as e:
                last_err = e
                print(f"[AI] {model_name} 생성 실패: {e}", file=sys.stderr)
    raise RuntimeError(f"모든 공급자 실패: {last_err}")

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
- 2번 빈칸 채우기(SHORT): **항상** 빈칸 채우기 형식으로 냅니다.
    · 교재 본문에 실제로 있는 문장(또는 핵심 표현)을 가져와, 그 주 메시지의 핵심어 한 자리를 빈칸 ______ (밑줄 6개)로 바꿉니다. 빈칸은 정확히 1개.
    · 형식 예: "교재는 영원한 천국에 들어갈 사람을 '끝까지 ______ 성도'라고 표현했습니다. 빈칸에 들어갈 말은 무엇일까요?" → 정답 "견디는"
    · 정답은 빈칸 자리에 그대로 들어가는 한 단어(띄어쓰기 없음)이며, 교재 본문에 그 형태 그대로 나와야 합니다.
    · 앞뒤 문맥만 보고도 정답이 하나로 정해져야 합니다. 인물·지명·고유명사, 어느 설교에나 맞는 일반어(사랑, 은혜, 믿음처럼 문맥 없이도 찍을 수 있는 단어)는 피하세요.
    · 설교 제목에 그대로 들어 있는 단어는 정답으로 쓰지 마세요(제목만 보고 맞힐 수 있음).
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
      "questionText": "교재는 ...을 '... ______ ...'라고 표현했습니다. 빈칸에 들어갈 말은 무엇일까요?",
      "correctAnswer": "빈칸에 들어갈 한 단어",
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

    def parse(text: str) -> dict:
        data = json.loads(_clean_json_response(text))
        if not isinstance(data, dict) or len(data.get("quizzes") or []) != 3:
            raise ValueError("퀴즈 3개 형식 아님")
        return data

    data, model_name = _generate(f"{SYSTEM_PROMPT}\n\n{user_prompt}", parse, attempts=2)
    data["generator"] = model_name

    # 2번은 항상 빈칸 채우기. 형식이 어긋나면 분석 전체를 다시 돌리지 않고 2번만 다시 만든다.
    quizzes = data["quizzes"]
    short = next((q for q in quizzes if q.get("stepNumber") == 2), None)
    problem = _cloze_problem(short, _build_material_context(sections)) if short else None
    if problem:
        print(f"[AI] 2번 빈칸 형식 위반({problem}) → 2번만 재생성", file=sys.stderr)
        try:
            fixed = regenerate_single_quiz(
                sections, 2,
                current_question=short.get("questionText") if short else None,
                other_questions=[q.get("questionText") for q in quizzes if q is not short],
            )
            data["quizzes"] = [fixed if q is short else q for q in quizzes]
        except RuntimeError as e:
            # 재생성까지 실패해도 분석은 살린다(검수 화면에서 사람이 고치거나 재생성).
            print(f"[AI] 2번 재생성 실패, 원본 유지: {e}", file=sys.stderr)
    return data


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
        "이 문제는 빈칸 채우기입니다. 절대 참/거짓(OX) 문장으로 만들지 마세요. "
        "교재 본문의 실제 문장에서 핵심어 한 자리를 빈칸 ______ (밑줄 6개, 정확히 1개)로 바꾸고 "
        "'빈칸에 들어갈 말은 무엇일까요?'로 묻습니다. "
        "correctAnswer는 빈칸에 그대로 들어가는 한 단어(띄어쓰기 없음)이며 교재 본문에 그 형태로 나와야 합니다."
    ),
    "ESSAY": "이 문제는 짧은 서술형입니다. OX·단답이 아니라 한두 문장으로 생각을 정리하게 하고, correctAnswer는 모범답안 문장입니다.",
}


_BLANK_RE = re.compile(r"_{3,}")


def _cloze_problem(quiz: dict, material: str) -> str | None:
    """2번 빈칸 채우기 형식 검사. 문제가 없으면 None, 있으면 사유. 빈칸 표기는 ______로 통일한다."""
    question = quiz.get("questionText") or ""
    ans = (quiz.get("correctAnswer") or "").strip()
    if len(_BLANK_RE.findall(question)) != 1:
        return "빈칸(______)이 정확히 1개가 아님"
    if not ans or any(c.isspace() for c in ans):
        return f"정답이 한 단어가 아님({ans!r})"
    if material and re.sub(r"\s", "", ans) not in re.sub(r"\s", "", material):
        return f"정답이 교재 본문에 없음({ans!r})"
    quiz["questionText"] = _BLANK_RE.sub("______", question)
    return None


def _validate_quiz_type(quiz: dict, q_type: str, material: str = "") -> bool:
    """생성 결과가 기대 유형과 실제로 맞는지(라벨이 아니라 내용/정답 기준) 검증."""
    ans = (quiz.get("correctAnswer") or "").strip()
    question = (quiz.get("questionText") or "").strip()
    if not question:
        return False
    upper = ans.upper()
    if q_type == "OX":
        return upper in ("O", "X")
    if q_type == "SHORT":
        # 단답형인데 정답이 O/X면 실제로는 OX형이 샌 것 → 거부. 형식은 항상 빈칸 채우기.
        return bool(ans) and upper not in ("O", "X") and _cloze_problem(quiz, material) is None
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

    def parse(text: str) -> dict:
        data = json.loads(_clean_json_response(text))
        # 모델이 배열/래핑으로 줄 수 있으니 방어적으로 단일 dict로 정규화
        if isinstance(data, dict) and "quizzes" in data and data["quizzes"]:
            data = data["quizzes"][0]
        if isinstance(data, list):
            data = data[0]
        data["stepNumber"] = step_number
        data["questionType"] = q_type  # 유형 라벨은 코드가 고정
        # 라벨만 고정하면 'OX 내용 + SHORT 라벨'이 새므로, 내용/정답으로 유형을 검증
        if not _validate_quiz_type(data, q_type, _build_material_context(sections)):
            raise ValueError(f"유형 불일치(기대 {q_type}, 정답={data.get('correctAnswer')!r})")
        return data

    try:
        data, _ = _generate(f"{SYSTEM_PROMPT}\n\n{user_prompt}", parse, attempts=3)
    except RuntimeError as e:
        raise RuntimeError(f"문제 재생성 실패: {e}")
    return data
