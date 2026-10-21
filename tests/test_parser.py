from datetime import date

from services.parser import check_gate, extract_meta, parse_obs_sections

# HWP 추출 결과 모양(문단 1개 = 줄 1개)을 흉내 낸 합성 교안. 실제 교재는 저장소에 넣지 않는다.
HWP_TEXT = """4/19 (주일) 청년회 OBS 교재 (인도자용)
I. 설교 제목 : 영혼의 도피성, 예수 그리스도 (민수기 강해 35)
II. 성경 말씀 (민수기 35:9-15)
III. 말씀 정리하기
도피성은 부지중에 살인한 자의 피난처였다.
1. 도피성에 대한 설명 중 맞는 것은?
 (1) 피난처입니다. (○, ×)
 (2) 이스라엘 백성만 들어갈 수 있었습니다. (○, ×)
2. 위인들 중 죽음을 스스로 해결한 사람이 있습니까?
 ▶ 알렉산더 대왕의 빈 손
※ 기독교의 관점을 살펴봅시다.
3. 예수님은 부활 후 어떻게 되었습니까?
 ▶ 사흘 만에 부활하셨다.
 5-1. 부활의 가장 확실한 증거는 무엇일까요?
 ▶ 제자들의 삶의 변화
IV. 적용하기
1. 예수님은 나의 도피성입니까?
"""


def _point(sections, n):
    return next(s for s in sections if s["type"] == "point" and s["number"] == n)


def test_paragraph_mode_keeps_title_level_notes_and_unknown_lines():
    secs = parse_obs_sections(HWP_TEXT, paragraph_mode=True)
    p2, p3 = _point(secs, 2), _point(secs, 3)
    # 하위 항목 없는 포인트 밑 ▶ 해설은 point.notes로 보존(예전엔 버려짐)
    assert p2["notes"] == ["알렉산더 대왕의 빈 손"]
    # 해설 뒤 규칙 밖 문단은 해설에 섞이지 않고 번호 없는 항목으로
    assert [i["text"] for i in p2["items"]] == ["※ 기독교의 관점을 살펴봅시다."]
    assert p2["items"][0]["number"] == ""
    assert p3["notes"] == ["사흘 만에 부활하셨다."]
    assert p3["items"][0]["text"] == "5-1. 부활의 가장 확실한 증거는 무엇일까요?"
    assert p3["items"][0]["notes"] == ["제자들의 삶의 변화"]
    assert check_gate(HWP_TEXT, secs)["missingLines"] == []


def test_numbering_skips_unnumbered_nodes():
    text = HWP_TEXT.replace("※ 기독교의 관점을 살펴봅시다.\n", "※ 기독교의 관점을 살펴봅시다.\n (1) 첫 번째 관점입니다.\n")
    p2 = _point(parse_obs_sections(text, paragraph_mode=True), 2)
    assert [i["number"] for i in p2["items"]] == ["", "(1)"]


def test_pdf_mode_still_joins_wrapped_lines():
    pdf = "III. 말씀 정리하기\n1. 첫 줄이\n이어지는 문장입니다.\n (1) 항목\nIV. 적용하기\n1. 적용\n"
    p1 = _point(parse_obs_sections(pdf), 1)
    assert p1["title"] == "첫 줄이 이어지는 문장입니다."


def test_extract_meta():
    meta = extract_meta(HWP_TEXT, today=date(2026, 4, 15))
    assert meta == {"title": "영혼의 도피성, 예수 그리스도", "biblePassage": "민수기 35:9-15", "publishedDate": "2026-04-19"}
    # 연말에 받은 1월 교안 → 다음 해로
    assert extract_meta("1/4 (주일) 교재", today=date(2025, 12, 30))["publishedDate"] == "2026-01-04"
    assert extract_meta("머리말 없음")["title"] is None


def test_gate_flags_other_template():
    old = "1. 설교 제목 : 이삭\n3. 말씀 정리하기\n(1) 족장\n"
    gate = check_gate(old, parse_obs_sections(old, paragraph_mode=True))
    assert gate["templateOk"] is False
    assert gate["warnings"]
