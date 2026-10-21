"""자체 HWP 리더 단위 테스트 — 실제 교재 없이 스펙(한글 문서 파일 형식 5.0)대로 레코드 바이트를 직접 조립한다."""
import io
import struct
import zlib

import pytest

from services import hwp_extractor as hx
from services.hwp_extractor import HwpError


def rec(tag: int, body: bytes, level: int = 0) -> bytes:
    size = len(body)
    if size >= 0xFFF:
        return struct.pack("<II", tag | level << 10 | 0xFFF << 20, size) + body
    return struct.pack("<I", tag | level << 10 | size << 20) + body


def wchars(s: str) -> bytes:
    return s.encode("utf-16-le")


def ctrl(code: int) -> bytes:
    # 인라인/확장 컨트롤: 코드 + 6 WCHAR + 코드 = 8 WCHAR
    return struct.pack("<H", code) + b"tbl " + b"\0" * 8 + struct.pack("<H", code)


def para_shape(head: int = 0, numbering_id: int = 0, level: int = 0) -> bytes:
    body = bytearray(54)
    struct.pack_into("<I", body, 0, head << 23 | level << 25)
    struct.pack_into("<H", body, 30, numbering_id)
    return rec(hx.TAG_PARA_SHAPE, bytes(body))


def numbering(formats: list[str]) -> bytes:
    body = b"".join(b"\0" * 12 + struct.pack("<H", len(f)) + wchars(f) for f in formats)
    return rec(hx.TAG_NUMBERING, body + struct.pack("<H", 1) + b"\0" * 28)


def para(shape_id: int, text: bytes | None, level: int = 0) -> bytes:
    out = rec(hx.TAG_PARA_HEADER, struct.pack("<IIHBBHHHIH", 0, 0, shape_id, 0, 0, 1, 0, 1, 0, 0), level)
    if text is not None:
        out += rec(hx.TAG_PARA_TEXT, text + wchars("\r"), level + 1)
    return out


def test_records_normal_and_extended_size():
    big = b"x" * 5000
    got = list(hx._records(rec(0x43, b"ab", level=2) + rec(0x43, big)))
    assert got == [(0x43, 2, b"ab"), (0x43, 0, big)]


def test_records_truncated_raises():
    with pytest.raises(HwpError, match="손상"):
        list(hx._records(rec(0x43, b"abcd")[:-1]))


class _Ole:
    def __init__(self, raw):
        self.raw = raw

    def openstream(self, name):
        return io.BytesIO(self.raw)


def test_read_stream_raw_deflate_and_corrupt():
    c = zlib.compressobj(wbits=-15)
    raw = c.compress(b"hello") + c.flush()
    assert hx._read_stream(_Ole(raw), "DocInfo", compressed=True) == b"hello"
    assert hx._read_stream(_Ole(b"plain"), "DocInfo", compressed=False) == b"plain"
    with pytest.raises(HwpError, match="압축 해제"):
        hx._read_stream(_Ole(b"\xff\xff\xff"), "DocInfo", compressed=True)


def test_para_text_skips_controls_and_keeps_surrogates():
    data = wchars("앞") + ctrl(11) + wchars("뒤") + ctrl(9) + struct.pack("<H", 31) + wchars("𝄞\r")
    assert hx._para_text(data) == "앞뒤𝄞"


def test_check_header_flags():
    def header(flags):
        return hx.SIGNATURE + b"\0" * 15 + struct.pack("<II", 0x05000300, flags) + b"\0" * 216

    assert hx._check_header(header(hx.FLAG_COMPRESSED)) is True
    assert hx._check_header(header(0)) is False
    with pytest.raises(HwpError, match="암호"):
        hx._check_header(header(hx.FLAG_PASSWORD))
    with pytest.raises(HwpError, match="배포용"):
        hx._check_header(header(hx.FLAG_COMPRESSED | hx.FLAG_DISTRIBUTION))
    with pytest.raises(HwpError, match="서명"):
        hx._check_header(b"not hwp" + b"\0" * 249)


def test_numbering_restored_in_document_order_with_table_cells():
    docinfo = numbering(["^1.", "^2)", "(^3)", "", "", "", ""]) + para_shape() + para_shape(2, 1, 0) + para_shape(2, 1, 1)
    numberings, shapes = hx._parse_docinfo(docinfo)
    section = (
        para(1, wchars("가"))
        + para(2, wchars("나"))
        + para(0, ctrl(11))  # 표를 담은 문단 — 셀 문단이 뒤따른다
        + rec(0x47, b" lbt", 1)  # CTRL_HEADER 'tbl '
        + rec(0x48, b"\0" * 6, 2)  # LIST_HEADER
        + para(2, wchars("  셀"), level=2)
        + para(2, None)  # 빈 번호 문단은 번호를 소비하지 않는다
        + para(1, wchars("다"))
        + para(2, wchars("라"))
    )
    got = hx._section_paragraphs(section, shapes, numberings, {})
    assert got == ["1. 가", "1) 나", "", "2) 셀", "", "2. 다", "1) 라"]


def test_unknown_para_shape_raises():
    with pytest.raises(HwpError, match="문단 모양"):
        hx._section_paragraphs(para(5, wchars("x")), [], [], {})


def test_rejects_hwpx_and_non_ole():
    with pytest.raises(HwpError, match="hwpx"):
        hx.extract_paragraphs_from_bytes(b"PK\x03\x04" + b"\0" * 100)
    with pytest.raises(HwpError, match="OLE"):
        hx.extract_text_from_bytes(b"garbage")
