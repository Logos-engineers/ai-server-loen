"""실제 HWP 교재로 하는 골든 테스트 — 교재는 저장소에 넣지 않으므로 로컬에서만:
    OBS_HWP_DIR=~/Downloads/교재폴더 pytest tests/test_hwp_golden.py
양식이 맞는 교재(templateOk)는 원문 줄이 하나도 빠지지 않아야 한다."""
import glob
import os

import pytest

from services.hwp_extractor import extract_text_from_bytes
from services.parser import check_gate, parse_obs_sections

HWP_DIR = os.path.expanduser(os.getenv("OBS_HWP_DIR", ""))
FILES = sorted(glob.glob(os.path.join(HWP_DIR, "**", "*.hwp"), recursive=True)) if HWP_DIR else []


@pytest.mark.skipif(not FILES, reason="OBS_HWP_DIR 미설정(로컬 전용)")
@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(f)[:30] for f in FILES])
def test_no_missing_lines(path):
    text = extract_text_from_bytes(open(path, "rb").read())
    gate = check_gate(text, parse_obs_sections(text, paragraph_mode=True))
    if not gate["templateOk"]:
        pytest.skip("양식 불일치 교재 — 게이트가 경고로 처리")
    assert gate["missingLines"] == []
