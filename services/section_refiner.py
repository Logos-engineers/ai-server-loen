"""규칙 파서(parser.py) 결과를 AI로 후보정하는 단계.

규칙 기반 파서는 PDF 줄바꿈/들여쓰기 때문에 (1) 한 문장이 여러 노드로 쪼개지거나
(2) 자식이어야 할 항목이 형제로 빠지는 등 '구조' 오류가 종종 난다.
이 모듈은 PDF 원문과 파서 초안 JSON을 함께 Gemini에 주고 **구조만** 바로잡는다.

설계 원칙:
- 규칙 파서는 그대로 두고 그 결과를 '교정'만 한다(처음부터 재파싱 아님).
- AI는 텍스트 끊기·계층만 손대고 글자는 원문 그대로 유지한다(오탈자/빈칸 수정 금지).
- number 필드는 AI를 믿지 않고 시스템이 결정적으로 재계산한다(_assign_numbers).
- 결과가 스키마 검증을 통과 못 하거나 내용이 크게 유실되면 **초안을 그대로 폴백**한다.
  → 보정이 실패해도 파이프라인이 깨지거나 지금보다 나빠지지 않는다.
"""

import google.generativeai as genai
import json
import os
import sys
from typing import Any

from services.parser import _assign_numbers

# quiz_generator.py와 동일하게 import 시점에 구성(키 없으면 generate 시점에만 실패).
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# 후보정은 '기계적 재구조화'라 경량 모델로 충분하고, flash(thinking)는 이 작업에
# 60~100s씩 걸려 analyze 전체를 타임아웃시켰다(QA). flash-lite로 지연을 크게 낮춘다.
_model = genai.GenerativeModel("gemini-2.5-flash-lite")

# 후보정 Gemini 호출 상한(초). 초과 시 예외→초안 폴백. 본 파이프라인을 길게 막지 않는다.
_REFINE_TIMEOUT_SEC = 40

_VALID_TYPES = {"intro", "point", "application"}

# 내용 유실 가드: 교정본 텍스트 총량이 초안의 이 비율 미만이면 AI가 내용을 날린 것으로 보고 폴백.
_MIN_VOLUME_RATIO = 0.7


def _refine_enabled() -> bool:
    # 기본 켜짐. 끄려면 ENABLE_SECTION_REFINE=false (kill switch).
    return os.getenv("ENABLE_SECTION_REFINE", "true").strip().lower() not in ("false", "0", "no", "off")


REFINE_PROMPT = """당신은 OBS 교안 파서의 후보정기입니다. 규칙 기반 파서가 PDF 텍스트를 구조화한 초안(JSON)을 드립니다.
PDF 원문과 대조해 **구조 오류만** 바로잡으세요.

【고치는 것 — 딱 두 가지】
1. 텍스트 끊김 오류: PDF 줄바꿈 때문에 한 문장이 여러 노드로 쪼개졌거나, 서로 다른 항목이 한 노드에 붙은 경우 → 원문 기준으로 올바르게 합치거나 나눈다.
2. 계층/중첩 오류: 어떤 항목이 다른 항목의 자식(children)이어야 하는데 형제로 빠졌거나 그 반대인 경우 → 올바른 부모-자식 관계로 재배치한다.

【절대 하지 말 것】
- 원문에 있는 글자를 바꾸거나 다듬지 마라(오탈자·띄어쓰기 교정 금지). 텍스트는 원문 그대로 옮긴다.
- 내용을 새로 만들거나(환각) 삭제하지 마라. 끊고/합치고/옮길 뿐, 글자 총량은 보존한다.
- answer의 빈칸 "( )"을 채우지 마라. 주어진 값을 그대로 둔다.
- type(intro/point/application)과 JSON 스키마(키 이름)를 바꾸지 마라.
- number 필드는 신경 쓰지 마라(시스템이 자동 재계산한다). 주어진 값을 그대로 둬도 된다.
- "III. 말씀 정리하기", "IV. 적용하기" 같은 섹션 제목 줄은 구조용 헤더다. 어떤 노드의 text/title에도 넣지 마라.

【스키마】 (입력과 동일한 구조로 출력)
- intro: {{ "type":"intro", "text": str }}
- point: {{ "type":"point", "number": int, "title": str, "answer": str|null, "reference": str, "items": [node] }}
- application: {{ "type":"application", "items": [node] }}
- node: {{ "number": str, "text": str, "answer": str|null, "numbered": bool, "children": [node], "notes": [str] }}

반드시 위 구조의 JSON 배열만 출력하세요. 설명·주석·마크다운 없이 JSON만.

[PDF 원문]
{pdf_text}

[파서 초안 JSON]
{draft_json}"""


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _as_text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _as_answer(v: Any) -> str | None:
    # answer는 채워진 단어(str) 또는 빈칸(null)만 허용.
    return v if isinstance(v, str) else None


def _normalize_node(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("node is not an object")
    return {
        "number": "",  # 아래에서 결정적으로 재계산
        "text": _as_text(raw.get("text")),
        "answer": _as_answer(raw.get("answer")),
        "numbered": bool(raw.get("numbered", True)),
        "children": [_normalize_node(c) for c in (raw.get("children") or [])],
        "notes": [n for n in (raw.get("notes") or []) if isinstance(n, str) and n.strip()],
    }


def _normalize_section(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("section is not an object")
    t = raw.get("type")
    if t == "intro":
        return {"type": "intro", "text": _as_text(raw.get("text"))}
    if t == "point":
        return {
            "type": "point",
            "number": 0,  # 아래에서 재계산
            "title": _as_text(raw.get("title")),
            "answer": _as_answer(raw.get("answer")),
            "reference": _as_text(raw.get("reference")),
            "items": [_normalize_node(n) for n in (raw.get("items") or [])],
        }
    if t == "application":
        return {
            "type": "application",
            "items": [_normalize_node(n) for n in (raw.get("items") or [])],
        }
    raise ValueError(f"unknown section type: {t!r}")


def _normalize_sections(raw_list: Any) -> list[dict[str, Any]]:
    """AI 응답을 정확한 스키마로 강제 정규화하고 number를 결정적으로 재계산한다.

    스키마에 안 맞으면 ValueError를 던져 호출측이 초안으로 폴백하게 한다.
    """
    if not isinstance(raw_list, list) or not raw_list:
        raise ValueError("sections is not a non-empty list")

    sections = [_normalize_section(s) for s in raw_list]

    point_no = 0
    for s in sections:
        if s["type"] == "point":
            point_no += 1
            s["number"] = point_no
            _assign_numbers(s["items"], 1)
        elif s["type"] == "application":
            _assign_numbers(s["items"], 0)
    return sections


def _text_volume(sections: list[dict[str, Any]]) -> int:
    """모든 텍스트(text/title/reference/notes)의 글자 수 합 — 내용 유실 감지용."""
    total = 0

    def walk_nodes(nodes: list) -> None:
        nonlocal total
        for n in nodes or []:
            total += len(n.get("text", "") or "")
            total += sum(len(x or "") for x in (n.get("notes") or []))
            walk_nodes(n.get("children") or [])

    for s in sections:
        total += len(s.get("text", "") or "")
        total += len(s.get("title", "") or "")
        total += len(s.get("reference", "") or "")
        walk_nodes(s.get("items") or [])
    return total


def refine_sections(pdf_text: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """규칙 파서 초안을 AI로 후보정. 실패하면 초안을 그대로 반환(폴백)."""
    if not _refine_enabled() or not sections:
        return sections

    try:
        draft_json = json.dumps(sections, ensure_ascii=False)
        prompt = REFINE_PROMPT.format(pdf_text=pdf_text, draft_json=draft_json)

        response = _model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0},
            request_options={"timeout": _REFINE_TIMEOUT_SEC},
        )
        raw = json.loads(_clean_json(response.text))
        if isinstance(raw, dict) and "sections" in raw:
            raw = raw["sections"]

        refined = _normalize_sections(raw)

        # 내용 유실 가드 — AI가 본문을 크게 날렸으면 초안이 더 안전하다.
        draft_volume = _text_volume(sections)
        if draft_volume and _text_volume(refined) < draft_volume * _MIN_VOLUME_RATIO:
            print("[AI] section refine rejected: content shrank too much, using draft", file=sys.stderr)
            return sections

        return refined
    except Exception as e:
        # 보정은 부가 단계 — 어떤 이유로든 실패하면 초안으로 안전 폴백.
        print(f"[AI] section refine skipped (fallback to draft): {e}", file=sys.stderr)
        return sections
