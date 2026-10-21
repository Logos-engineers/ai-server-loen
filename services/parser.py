import re
from datetime import date
from typing import Any

PREFIX_PATTERNS = [
    ("d1", re.compile(r"^(\d+)\.\s*(.+)$")),
    ("d2", re.compile(r"^\((\d+)\)\s*(.+)$")),
    ("d3", re.compile(r"^(\d+)\)\s*(.+)$")),
    ("d4", re.compile(r"^([①②③④⑤⑥⑦⑧⑨⑩])\s*(.+)$")),
    ("d5", re.compile(r"^([a-z])\.\s*(.+)$")),
    ("note", re.compile(r"^▶\s*(.+)$")),
]

CHILD_DEPTH_BY_KIND = {
    "d2": 1,
    "d3": 2,
    "d4": 3,
    "d5": 4,
}


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _is_page_marker(line: str) -> bool:
    return bool(re.match(r"^-\d+-$", line))


def _append_text(base: str, addition: str) -> str:
    if not base:
        return addition
    if not addition:
        return base

    if addition == ")":
        return f"{base})"

    if addition.startswith((")", ",", ".", "?", "!", ":", ";")):
        return f"{base}{addition}"

    if base.endswith(("(", "“", '"')):
        return f"{base}{addition}"

    return f"{base} {addition}"


def _strip_soft_prefix(line: str) -> str:
    cleaned = line.strip()
    if cleaned.startswith("- "):
        return cleaned[2:].strip()
    if cleaned == "-":
        return ""
    return cleaned


def _is_question_text(text: str) -> bool:
    normalized = text.strip()
    return normalized.endswith("?") or normalized.endswith("？") or normalized.endswith("니까")


# 해설(▶) 바로 뒤 문단 중 "참여자에게 보여야 하는" 것: 안내(※), 하위 질문 번호(5-1. / 2-1) / 4-(1)), 질문 문장.
# 그 밖의 문단은 해설의 둘째 문단(성경 인용·설명)이라 해설에 이어붙인다(PDF 경로와 같은 결과).
_VISIBLE_AFTER_NOTE = re.compile(r"^(※|Q\.|\d+-\d+[\.\)]|\d+-\()")


def _is_visible_after_note(text: str) -> bool:
    return bool(_VISIBLE_AFTER_NOTE.match(text)) or _is_question_text(text)


def _classify_line(line: str) -> tuple[str, str]:
    cleaned = line.strip()
    if cleaned.startswith("- "):
        return "dash", _normalize_line(cleaned[2:])
    if cleaned == "-":
        return "text", ""

    for kind, pattern in PREFIX_PATTERNS:
        match = pattern.match(line)
        if match:
            group_index = 1 if kind == "note" else 2
            return kind, _normalize_line(match.group(group_index))
    return "text", _normalize_line(_strip_soft_prefix(line))


def _extract_section_lines(pdf_text: str) -> tuple[list[str], list[str]]:
    intro_and_study: list[str] = []
    application: list[str] = []
    current: list[str] | None = None

    for raw_line in pdf_text.splitlines():
        line = raw_line.rstrip()
        normalized = line.strip()
        if not normalized or _is_page_marker(normalized):
            continue
        if normalized.startswith("III. 말씀 정리하기"):
            current = intro_and_study
            continue
        if normalized.startswith("IV. 적용하기"):
            current = application
            continue
        if current is not None:
            current.append(line)

    return intro_and_study, application


def _collect_entries(lines: list[str], paragraph_mode: bool = False) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current_kind: str | None = None
    current_text = ""

    def flush() -> None:
        nonlocal current_kind, current_text
        if current_kind and current_text.strip():
            entries.append({"kind": current_kind, "text": current_text.strip()})
        current_kind = None
        current_text = ""

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue

        if paragraph_mode and stripped == "▶":
            # 기호만 있는 줄 — 해설 본문은 다음 문단에 온다.
            flush()
            current_kind, current_text = "note", ""
            continue

        kind, text = _classify_line(stripped)
        if kind != "text":
            flush()
            current_kind = kind
            current_text = text
            continue

        if paragraph_mode and current_kind == "note" and not _is_visible_after_note(text):
            current_text = _append_text(current_text, text)  # 해설의 다음 문단
        elif current_kind is None or paragraph_mode:
            # 문단 모드(HWP): 한 줄이 완결된 문단 — 보이는 내용이 해설에 묻혀 사라지지 않게 새 항목으로.
            flush()
            current_kind = "text"
            current_text = text
        else:
            current_text = _append_text(current_text, text)

    flush()
    return entries


def _make_node(text: str) -> dict[str, Any]:
    return {
        "number": "",
        "text": text,
        "answer": None,
        "numbered": True,
        "children": [],
        "notes": [],
    }


def _format_number(depth: int, index: int) -> str:
    if depth <= 0:
        return f"{index}."
    if depth == 1:
        return f"({index})"
    if depth == 2:
        return f"{index})"
    if depth == 3:
        return ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"][index - 1]
    return f"{chr(96 + index)}."


def _assign_numbers(nodes: list[dict[str, Any]], depth: int) -> None:
    idx = 0
    for node in nodes:
        if node.get("numbered", True):
            idx += 1
            node["number"] = _format_number(depth, idx)
        else:
            node["number"] = ""
        _assign_numbers(node.get("children", []), depth + 1)


def _build_study_sections(entries: list[dict[str, str]], paragraph_mode: bool = False) -> list[dict[str, Any]]:
    intro_parts: list[str] = []
    points: list[dict[str, Any]] = []
    current_point: dict[str, Any] | None = None
    node_stack: list[tuple[dict[str, Any], int]] = []
    prev_kind: str | None = None

    for entry in entries:
        kind = entry["kind"]
        text = entry["text"]
        last_kind, prev_kind = prev_kind, kind

        if kind == "text" and current_point is None:
            intro_parts.append(text)
            continue

        if kind == "d1":
            current_point = {
                "type": "point",
                "number": len(points) + 1,
                "title": text,
                "answer": None,
                "reference": "",
                "items": [],
            }
            points.append(current_point)
            node_stack = []
            continue

        if current_point is None:
            intro_parts.append(text)
            continue

        if kind == "note":
            if node_stack:
                node_stack[-1][0]["notes"].append(text)
            else:
                current_point.setdefault("notes", []).append(text)
            continue

        if kind in CHILD_DEPTH_BY_KIND:
            depth = CHILD_DEPTH_BY_KIND[kind]
            node = _make_node(text)

            while node_stack and node_stack[-1][1] >= depth:
                node_stack.pop()

            if depth == 1 or not node_stack:
                current_point["items"].append(node)
            else:
                node_stack[-1][0]["children"].append(node)

            node_stack.append((node, depth))
            continue

        if kind == "dash" and node_stack:
            if _is_question_text(text):
                parent, parent_rank = node_stack[-1]
                node = _make_node(text)
                node["numbered"] = False
                parent["children"].append(node)
                node_stack.append((node, parent_rank))
            else:
                node_stack[-1][0]["text"] = _append_text(node_stack[-1][0]["text"], text)
            continue

        if paragraph_mode and last_kind == "note":
            # 해설 뒤 "※ …", "5-1. …" 같은 보이는 문단 — 제목이나 해설에 섞지 않고 번호 없는 항목으로 보존.
            node = _make_node(text)
            node["numbered"] = False
            current_point["items"].append(node)
            node_stack = [(node, 1)]
            continue

        if node_stack:
            node_stack[-1][0]["text"] = _append_text(node_stack[-1][0]["text"], text)
        else:
            current_point["title"] = _append_text(current_point["title"], text)

    for point in points:
        _assign_numbers(point["items"], 1)

    sections: list[dict[str, Any]] = []
    if intro_parts:
        sections.append(
            {
                "type": "intro",
                "text": " ".join(intro_parts).strip(),
            }
        )
    sections.extend(points)
    return sections


def _build_application_section(entries: list[dict[str, str]]) -> dict[str, Any] | None:
    if not entries:
        return None

    roots: list[dict[str, Any]] = []
    node_stack: list[dict[str, Any]] = []

    for entry in entries:
        kind = entry["kind"]
        text = entry["text"]

        if kind == "note":
            target = node_stack[-1] if node_stack else None
            if target is not None:
                target["notes"].append(text)
            continue

        if kind == "d1":
            node = _make_node(text)
            roots.append(node)
            node_stack = [node]
            continue

        if kind in CHILD_DEPTH_BY_KIND:
            depth = CHILD_DEPTH_BY_KIND[kind]
            node = _make_node(text)

            while len(node_stack) > depth:
                node_stack.pop()

            parent = node_stack[-1] if node_stack else None
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
            node_stack.append(node)
            continue

        if node_stack:
            node_stack[-1]["text"] = _append_text(node_stack[-1]["text"], text)
        else:
            # 첫 번호 항목 앞의 문단(성경 구절 인용·진행 안내 등) — 예전엔 버려졌다. 번호 없는 항목으로 보존.
            node = _make_node(text)
            node["numbered"] = False
            roots.append(node)
            node_stack = [node]

    _assign_numbers(roots, 0)
    return {
        "type": "application",
        "items": roots,
    }


def parse_obs_sections(pdf_text: str, paragraph_mode: bool = False) -> list[dict[str, Any]]:
    """paragraph_mode=True: 입력의 한 줄 = 완결된 문단(HWP 추출). False: PDF 줄바꿈 텍스트."""
    intro_and_study_lines, application_lines = _extract_section_lines(pdf_text)
    study_entries = _collect_entries(intro_and_study_lines, paragraph_mode)
    application_entries = _collect_entries(application_lines, paragraph_mode)

    sections = _build_study_sections(study_entries, paragraph_mode)
    application = _build_application_section(application_entries)
    if application is not None:
        sections.append(application)
    return sections


# ── 메타데이터 · 게이트 ─────────────────────────────────────────────────────────

_TITLE_RE = re.compile(r"설교\s*제목\s*[:：]\s*(.+?)\s*$", re.M)
_PASSAGE_RE = re.compile(r"성경\s*말씀\s*\(([^)]+)\)")
_DATE_RE = re.compile(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\(\s*주일\s*\)", re.M)
_TRAILING_SERIES_RE = re.compile(r"\s*\([^()]*\)\s*$")  # "제목 (민수기 강해 35)" → 시리즈 표기 제거


def extract_meta(text: str, today: date | None = None) -> dict[str, str | None]:
    """교안 머리말에서 제목·본문구절·발행일을 뽑는다. 못 찾으면 None(사람이 채움).
    날짜는 "M/D (주일)"만 있어 연도가 없다 → 기준일과 가장 가까운 연도로 정한다."""
    today = today or date.today()
    title = passage = published = None

    m = _TITLE_RE.search(text)
    if m:
        title = _TRAILING_SERIES_RE.sub("", m.group(1)).strip() or None
    m = _PASSAGE_RE.search(text)
    if m:
        passage = m.group(1).strip()
    m = _DATE_RE.search(text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        candidates = []
        for year in (today.year - 1, today.year, today.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                pass
        if candidates:
            published = min(candidates, key=lambda d: abs((d - today).days)).isoformat()

    return {"title": title, "biblePassage": passage, "publishedDate": published}


def _norm(s: str) -> str:
    return re.sub(r"[\s\"“”‘’'·]", "", s)


def _all_strings(o: Any) -> list[str]:
    if isinstance(o, dict):
        return [x for v in o.values() for x in _all_strings(v)]
    if isinstance(o, list):
        return [x for v in o for x in _all_strings(v)]
    return [str(o)] if isinstance(o, (str, int)) and o != "" else []


def check_gate(text: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    """양식 검사 + 누락 검사. 결과는 막지 않고 알린다(Slack 카드/검수 화면 경고용).
    - templateOk: III·IV 섹션, 포인트 1개 이상, 적용 섹션 — 202개 코퍼스에서 양식 불일치를 정확히 갈랐다.
    - missingLines: "III. 말씀 정리하기" 이후 원문 줄 중 결과 어디에도 없는 것(조용한 유실 감지)."""
    has_study = any(l.strip().startswith("III. 말씀 정리하기") for l in text.splitlines())
    has_app = any(l.strip().startswith("IV. 적용하기") for l in text.splitlines())
    points = sum(1 for s in sections if s.get("type") == "point")
    has_app_section = any(s.get("type") == "application" for s in sections)
    template_ok = has_study and has_app and points > 0 and has_app_section

    blob = _norm(" ".join(_all_strings(sections)))
    missing: list[str] = []
    in_region = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("III. 말씀 정리하기"):
            in_region = True
            continue
        if not in_region or not line or line == "▶" or line.startswith("IV. 적용하기") or _is_page_marker(line):
            continue
        _, body = _classify_line(line)
        if _norm(body) and _norm(body) not in blob:
            missing.append(line[:120])

    warnings = []
    if not template_ok:
        warnings.append("양식 불일치: 'III. 말씀 정리하기'/'IV. 적용하기' 구조를 찾지 못했습니다. 수동 확인이 필요합니다.")
    if missing:
        warnings.append(f"원문 {len(missing)}줄이 결과에 없습니다.")
    return {"templateOk": template_ok, "missingLines": missing, "warnings": warnings}
