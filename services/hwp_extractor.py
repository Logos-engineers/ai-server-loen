"""HWP(한글) 교안 → 문단 텍스트. PDF 변환 없이 pyhwp로 원본 구조를 직접 읽는다.

- 문단 1개 = 줄 1개로 돌려준다(PDF처럼 줄바꿈으로 문장이 쪼개지지 않음) → 파서 문단 모드용.
- 표 안의 문단(서론 박스 등)도 문서 순서대로 포함한다. hwp5txt는 표를 '<표>'로 날린다.
- 자동번호 문단은 번호 글자가 본문에 없다 → 문단 모양(head-shape=number)과 번호 정의(^1.)로 복원.
  복원하지 않으면 "1." 항목이 사라져 포인트 섹션이 통째로 유실된다(PoC 0405).
"""

import io
import os
import re
import tempfile
import xml.etree.ElementTree as ET

from hwp5.xmlmodel import Hwp5File


def _hwp_to_xml(data: bytes) -> bytes:
    # pyhwp(olefile)는 파일 경로로 여는 게 가장 안정적이라 임시 파일을 거친다.
    fd, path = tempfile.mkstemp(suffix=".hwp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        hwp = Hwp5File(path)
        try:
            out = io.BytesIO()
            hwp.xmlevents(embedbin=False).dump(out)
            return out.getvalue()
        finally:
            hwp.close()
    finally:
        os.remove(path)


def _paragraph_text(p: ET.Element) -> str:
    # 문단 자신의 글자만. 표가 들어 있는 문단은 표 셀 문단이 별도 Paragraph로 순회되므로 제외.
    own = "".join(t.text or "" for t in p.findall("./LineSeg/Text")) or "".join(
        t.text or "" for t in p.findall("./Text")
    )
    if own or list(p.iter("TableControl")):
        return own
    return "".join(t.text or "" for t in p.iter("Text"))


def extract_paragraphs_from_bytes(data: bytes) -> list[str]:
    root = ET.fromstring(_hwp_to_xml(data))
    numberings = [[lv.get("numbering-format") for lv in n.iter("NumberingLevel")] for n in root.iter("Numbering")]
    shapes = list(root.iter("ParaShape"))
    counters: dict[int, list[int]] = {}

    paragraphs: list[str] = []
    for p in root.iter("Paragraph"):
        text = _paragraph_text(p)
        shape = shapes[int(p.get("parashape-id", 0))]
        if shape.get("head-shape") == "number" and text.strip():
            nid, level = int(shape.get("numbering-bullet-id", 0)), int(shape.get("level", 0))
            c = counters.setdefault(nid, [0] * 7)
            c[level] += 1
            for i in range(level + 1, 7):
                c[i] = 0
            fmt = numberings[nid - 1][level] if 0 < nid <= len(numberings) and level < len(numberings[nid - 1]) else "^1."
            prefix = re.sub(r"\^(\d)", lambda m: str(c[int(m.group(1)) - 1]), fmt or "^1.")
            text = f"{prefix} {text.lstrip()}"
        paragraphs.append(text)
    return paragraphs


def extract_text_from_bytes(data: bytes) -> str:
    return "\n".join(extract_paragraphs_from_bytes(data))
