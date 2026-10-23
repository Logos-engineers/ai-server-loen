import pytest
from fastapi.testclient import TestClient

import routers.obs as obs
from main import app
from tests.test_parser import HWP_TEXT

QUIZ = {"summaries": ["a", "b", "c"], "quizzes": [{"stepNumber": 1}], "generator": "claude-opus-5"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(obs, "INTERNAL_API_TOKEN", "t")
    titles = []
    monkeypatch.setattr(obs, "generate_quizzes", lambda sections, title=None: titles.append(title) or QUIZ)
    monkeypatch.setattr(obs, "_titles_seen", titles, raising=False)
    return TestClient(app)


def test_hwp_path_skips_refiner_and_returns_meta_gate(client, monkeypatch):
    monkeypatch.setattr(obs, "download_file", lambda key: b"hwp")
    monkeypatch.setattr(obs, "extract_hwp_text", lambda data: HWP_TEXT)
    monkeypatch.setattr(obs, "refine_sections", lambda *a: pytest.fail("HWP 경로는 refiner를 타면 안 된다"))
    r = client.post("/obs/process", json={"r2_key": "dev/obs/abc.hwp"}, headers={"X-Internal-Token": "t"})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "영혼의 도피성, 예수 그리스도"
    assert body["gate"]["templateOk"] is True and body["gate"]["missingLines"] == []
    assert body["generator"] == "claude-opus-5" and body["summary"] == ["a", "b", "c"]
    assert obs._titles_seen == ["영혼의 도피성, 예수 그리스도"]  # 제목 단어를 2번 정답에서 빼려고 넘긴다


def test_pdf_path_still_refines(client, monkeypatch):
    called = []
    monkeypatch.setattr(obs, "extract_text_from_r2", lambda key: HWP_TEXT)
    monkeypatch.setattr(obs, "refine_sections", lambda text, secs: called.append(1) or secs)
    r = client.post("/obs/process", json={"r2_key": "obs/abc.pdf"}, headers={"X-Internal-Token": "t"})
    assert r.status_code == 200 and called == [1]


@pytest.mark.parametrize("key", ["obs/abc.docx", "obs/../x.hwp", "other/abc.hwp"])
def test_rejects_other_keys(client, key):
    r = client.post("/obs/process", json={"r2_key": key}, headers={"X-Internal-Token": "t"})
    assert r.status_code == 400
