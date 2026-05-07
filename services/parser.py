import re
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


def _collect_entries(lines: list[str]) -> list[dict[str, str]]:
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

        kind, text = _classify_line(stripped)
        if kind != "text":
            flush()
            current_kind = kind
            current_text = text
            continue

        if current_kind is None:
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
    for idx, node in enumerate(nodes, start=1):
        node["number"] = _format_number(depth, idx) if node.get("numbered", True) else ""
        _assign_numbers(node.get("children", []), depth + 1)


def _build_study_sections(entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    intro_parts: list[str] = []
    points: list[dict[str, Any]] = []
    current_point: dict[str, Any] | None = None
    node_stack: list[tuple[dict[str, Any], int]] = []

    for entry in entries:
        kind = entry["kind"]
        text = entry["text"]

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
            target = node_stack[-1][0] if node_stack else None
            if target is not None:
                target["notes"].append(text)
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

    _assign_numbers(roots, 0)
    return {
        "type": "application",
        "items": roots,
    }


def parse_obs_sections(pdf_text: str) -> list[dict[str, Any]]:
    intro_and_study_lines, application_lines = _extract_section_lines(pdf_text)
    study_entries = _collect_entries(intro_and_study_lines)
    application_entries = _collect_entries(application_lines)

    sections = _build_study_sections(study_entries)
    application = _build_application_section(application_entries)
    if application is not None:
        sections.append(application)
    return sections
