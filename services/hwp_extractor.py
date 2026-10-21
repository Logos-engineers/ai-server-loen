"""HWP(한글) 교안 → 문단 텍스트. 「한글 문서 파일 형식 5.0」(한글과컴퓨터 공개 스펙, revision 1.3)대로 직접 읽는다.

- 문단 1개 = 줄 1개로 돌려준다(PDF처럼 줄바꿈으로 문장이 쪼개지지 않음) → 파서 문단 모드용.
- 표 셀·글상자 등 컨트롤 안의 문단도 문서 순서대로 포함한다(레코드가 문서 순서로 직렬화되어 있음).
- 자동번호 문단은 번호 글자가 본문에 없다 → 문단 모양(머리 모양=번호)과 번호 정의(^1.)로 복원.
  복원하지 않으면 "1." 항목이 사라져 포인트 섹션이 통째로 유실된다(PoC 0405).

지원 범위: HWP 5.x 일반 문서. 배포용·암호 문서와 .hwpx(XML)는 지원하지 않는다(명확한 예외).
"""

import io
import re
import struct
import zlib

import olefile

SIGNATURE = b"HWP Document File"  # 표 3 파일 인식 정보
FLAG_COMPRESSED, FLAG_PASSWORD, FLAG_DISTRIBUTION = 0x1, 0x2, 0x4  # 표 3 속성 bit 0~2

TAG_NUMBERING = 0x10 + 7  # 표 13 HWPTAG_BEGIN+7
TAG_PARA_SHAPE = 0x10 + 9  # 표 13 HWPTAG_BEGIN+9
TAG_PARA_HEADER = 0x10 + 50  # 표 57 HWPTAG_BEGIN+50
TAG_PARA_TEXT = 0x10 + 51

HEAD_NUMBER = 2  # 표 44 bit 23~24 문단 머리 모양 종류: 번호
LEVELS = 7
# 표 6 제어 문자 중 크기 1인 문자 컨트롤(0, 10, 13, 24~31). 나머지 0~31은 8 WCHAR(16바이트)를 차지한다.
# 문자 컨트롤은 버린다 — 30/31(묶음·고정폭 빈칸)도 공백으로 살리면 기존 추출 결과와 섹션이 달라진다(골든 3건).
CHAR_CONTROLS = {0, 10, 13, *range(24, 32)}


class HwpError(ValueError):
    """읽을 수 없는 HWP(손상·암호·배포용·형식 아님)."""


def _records(data: bytes):
    # 레코드 헤더 32bit = TagID 10 | Level 10 | Size 12, Size=0xFFF면 DWORD 길이가 뒤따른다(4.1 데이터 레코드).
    pos, end = 0, len(data)
    while pos < end:
        if pos + 4 > end:
            raise HwpError("손상된 HWP: 레코드 헤더가 잘렸습니다")
        (hdr,) = struct.unpack_from("<I", data, pos)
        pos += 4
        tag, level, size = hdr & 0x3FF, (hdr >> 10) & 0x3FF, hdr >> 20
        if size == 0xFFF:
            if pos + 4 > end:
                raise HwpError("손상된 HWP: 확장 레코드 길이가 잘렸습니다")
            (size,) = struct.unpack_from("<I", data, pos)
            pos += 4
        if pos + size > end:
            raise HwpError(f"손상된 HWP: 레코드(tag={tag}) 길이가 스트림을 넘습니다")
        yield tag, level, data[pos : pos + size]
        pos += size


def _read_stream(ole: olefile.OleFileIO, name: str, compressed: bool) -> bytes:
    raw = ole.openstream(name).read()
    if not compressed:
        return raw
    try:
        return zlib.decompress(raw, -15)  # 헤더 없는 raw deflate
    except zlib.error as e:
        raise HwpError(f"손상된 HWP: {name} 압축 해제 실패 ({e})") from e


def _para_text(data: bytes) -> str:
    out, i, n = [], 0, len(data) // 2
    chars = struct.unpack_from(f"<{n}H", data)
    while i < n:
        c = chars[i]
        if c >= 32:
            out.append(c)
            i += 1
        elif c in CHAR_CONTROLS:
            i += 1
        else:
            i += 8  # 인라인/확장 컨트롤: 코드 + 6 WCHAR 정보 + 코드
    # 코드 단위로 모았다가 한 번에 디코딩해야 BMP 밖 글자(서로게이트 쌍)가 깨지지 않는다.
    return struct.pack(f"<{len(out)}H", *out).decode("utf-16-le", "replace")


def _numbering_formats(data: bytes) -> list[str]:
    # 표 38: (문단 머리 정보 + WORD len + WCHAR[len]) × 7. 표 39는 '8바이트'라 적혀 있지만 필드 합(UINT+2+2+UINT)은 12.
    formats, pos = [], 0
    for _ in range(LEVELS):
        pos += 12
        (length,) = struct.unpack_from("<H", data, pos)
        pos += 2
        formats.append(data[pos : pos + 2 * length].decode("utf-16-le", "replace"))
        pos += 2 * length
    return formats


def _parse_docinfo(data: bytes) -> tuple[list[list[str]], list[tuple[int, int, int]]]:
    numberings, shapes = [], []
    for tag, _, body in _records(data):
        if tag == TAG_NUMBERING:
            numberings.append(_numbering_formats(body))
        elif tag == TAG_PARA_SHAPE:
            # 표 43: 속성1(UINT32) … 오프셋 30에 번호/글머리표 ID(UINT16). 표 44: bit 23~24 머리 모양, 25~27 수준.
            (attr,) = struct.unpack_from("<I", body, 0)
            (nid,) = struct.unpack_from("<H", body, 30)
            shapes.append(((attr >> 23) & 0x3, nid, (attr >> 25) & 0x7))
    return numberings, shapes


def _check_header(header: bytes) -> bool:
    """FileHeader를 검사하고 BodyText 압축 여부를 돌려준다."""
    if not header.startswith(SIGNATURE) or len(header) < 40:
        raise HwpError("HWP 5.0 문서가 아닙니다(FileHeader 서명 불일치)")
    (flags,) = struct.unpack_from("<I", header, 36)
    if flags & FLAG_PASSWORD:
        raise HwpError("암호가 걸린 HWP 문서는 지원하지 않습니다")
    if flags & FLAG_DISTRIBUTION:
        raise HwpError("배포용 HWP 문서는 지원하지 않습니다. 일반 문서로 저장해 주세요")
    return bool(flags & FLAG_COMPRESSED)


def _section_paragraphs(stream: bytes, shapes, numberings, counters) -> list[str]:
    # PARA_HEADER는 표 셀·글상자 안 문단까지 문서 순서대로 직렬화돼 있다 → 등장 순서 그대로가 문서 순서.
    paras: list[list] = []  # [문단 모양 ID, 텍스트]
    for tag, _, body in _records(stream):
        if tag == TAG_PARA_HEADER:
            paras.append([struct.unpack_from("<H", body, 8)[0], ""])  # 표 58: 오프셋 8 문단 모양 ID
        elif tag == TAG_PARA_TEXT and paras:
            paras[-1][1] = _para_text(body)
    return [_numbered(text, shapes, shape_id, numberings, counters) for shape_id, text in paras]


def _numbered(text, shapes, shape_id, numberings, counters) -> str:
    if shape_id >= len(shapes):
        raise HwpError(f"손상된 HWP: 문단 모양 {shape_id}이 DocInfo에 없습니다")
    head, nid, level = shapes[shape_id]
    if head != HEAD_NUMBER or not text.strip():
        return text
    level = min(level, LEVELS - 1)  # 3비트라 7까지 올 수 있지만 번호 정의는 7수준(0~6)뿐
    c = counters.setdefault(nid, [0] * LEVELS)
    c[level] += 1
    c[level + 1 :] = [0] * (LEVELS - level - 1)  # 상위 수준이 증가하면 하위 수준은 다시 1부터
    fmt = numberings[nid - 1][level] if 0 < nid <= len(numberings) else "^1."
    prefix = re.sub(r"\^([1-7])", lambda m: str(c[int(m.group(1)) - 1]), fmt or "^1.")
    return f"{prefix} {text.lstrip()}"


def extract_paragraphs_from_bytes(data: bytes) -> list[str]:
    if not olefile.isOleFile(io.BytesIO(data)):
        if data[:2] == b"PK":
            raise HwpError(".hwpx(XML 기반) 문서는 지원하지 않습니다. HWP 5.0(.hwp)로 저장해 주세요")
        raise HwpError("HWP 5.0 문서가 아닙니다(OLE 컨테이너 아님)")
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception as e:
        raise HwpError(f"손상된 HWP: OLE 컨테이너를 열 수 없습니다 ({e})") from e
    try:
        if not ole.exists("FileHeader") or not ole.exists("DocInfo"):
            raise HwpError("HWP 5.0 문서가 아닙니다(FileHeader/DocInfo 없음)")
        compressed = _check_header(ole.openstream("FileHeader").read())
        numberings, shapes = _parse_docinfo(_read_stream(ole, "DocInfo", compressed))
        sections = sorted(
            (e[1] for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and re.fullmatch(r"Section\d+", e[1])),
            key=lambda s: int(s[len("Section") :]),
        )
        if not sections:
            raise HwpError("손상된 HWP: BodyText/Section 스트림이 없습니다")
        counters: dict[int, list[int]] = {}  # 번호 ID별 수준 카운터 — 구역이 바뀌어도 이어진다
        paragraphs: list[str] = []
        for name in sections:
            paragraphs += _section_paragraphs(_read_stream(ole, f"BodyText/{name}", compressed), shapes, numberings, counters)
        return paragraphs
    except struct.error as e:
        raise HwpError(f"손상된 HWP: 레코드가 너무 짧습니다 ({e})") from e
    finally:
        ole.close()


def extract_text_from_bytes(data: bytes) -> str:
    return "\n".join(extract_paragraphs_from_bytes(data))
