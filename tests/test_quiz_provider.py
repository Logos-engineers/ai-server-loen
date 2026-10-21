import json

import anthropic
import httpx2 as httpx
import pytest

import services.quiz_generator as qg

SECTIONS = [{"type": "intro", "text": "배경"}, {"type": "point", "number": 1, "title": "제목", "items": []}]
GOOD = json.dumps({"summaries": ["a", "b", "c"], "quizzes": [
    {"stepNumber": 1, "questionType": "OX", "questionText": "q1", "correctAnswer": "X", "explanation": "e"},
    {"stepNumber": 2, "questionType": "SHORT", "questionText": "q2", "correctAnswer": "감사", "explanation": "e"},
    {"stepNumber": 3, "questionType": "ESSAY", "questionText": "q3", "correctAnswer": "답", "explanation": "e"},
]})


def _api_error():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIStatusError("credit", response=httpx.Response(400, request=req), body=None)


@pytest.fixture
def calls(monkeypatch):
    log = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("QUIZ_PROVIDER", "claude")
    return log


def test_no_key_uses_gemini_only(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert qg._providers() == ["gemini"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("QUIZ_PROVIDER", "gemini")
    assert qg._providers() == ["gemini"]


def test_claude_success(monkeypatch, calls):
    monkeypatch.setattr(qg, "_complete", lambda p, prompt: calls.append(p) or GOOD)
    out = qg.generate_quizzes(SECTIONS)
    assert calls == ["claude"] and out["generator"] == qg.CLAUDE_MODEL


def test_claude_api_error_falls_back_without_retry(monkeypatch, calls):
    def fake(p, prompt):
        calls.append(p)
        if p == "claude":
            raise _api_error()
        return GOOD
    monkeypatch.setattr(qg, "_complete", fake)
    out = qg.generate_quizzes(SECTIONS)
    assert calls == ["claude", "gemini"] and out["generator"] == qg.GEMINI_MODEL


def test_bad_json_retries_then_falls_back(monkeypatch, calls):
    monkeypatch.setattr(qg, "_complete", lambda p, prompt: calls.append(p) or ("not json" if p == "claude" else GOOD))
    out = qg.generate_quizzes(SECTIONS)
    assert calls == ["claude", "claude", "gemini"] and out["generator"] == qg.GEMINI_MODEL


def test_notes_not_in_quiz_input():
    secs = [{"type": "point", "number": 1, "title": "t", "items": [
        {"number": "(1)", "text": "보이는 항목", "children": [], "notes": ["인도자만 보는 해설"]}]}]
    ctx = qg._build_material_context(secs)
    assert "보이는 항목" in ctx and "인도자만 보는 해설" not in ctx
