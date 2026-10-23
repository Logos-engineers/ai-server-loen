import json

import anthropic
import httpx2 as httpx
import pytest

import services.quiz_generator as qg

SECTIONS = [{"type": "intro", "text": "은혜를 받은 사람은 감사로 반응한다."}, {"type": "point", "number": 1, "title": "제목", "items": []}]
GOOD = json.dumps({"summaries": ["a", "b", "c"], "quizzes": [
    {"stepNumber": 1, "questionType": "OX", "questionText": "q1", "correctAnswer": "X", "explanation": "e"},
    {"stepNumber": 2, "questionType": "SHORT", "questionText": "은혜를 받은 사람은 ____로 반응한다. 빈칸에 들어갈 말은?", "correctAnswer": "감사", "explanation": "e"},
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


def test_cloze_problem_rules():
    material = "은혜를 받은 사람은 감사로 반응한다."
    ok = {"questionText": "은혜를 받은 사람은 ___로 반응한다.", "correctAnswer": "감사"}
    assert qg._cloze_problem(ok, material) is None and "______" in ok["questionText"]  # 표기 통일
    assert qg._cloze_problem({"questionText": "무엇으로 반응하나요?", "correctAnswer": "감사"}, material)  # 빈칸 없음
    assert qg._cloze_problem({"questionText": "____ ____", "correctAnswer": "감사"}, material)  # 빈칸 2개
    assert qg._cloze_problem({"questionText": "____로 반응", "correctAnswer": "감사 기도"}, material)  # 두 단어
    assert qg._cloze_problem({"questionText": "____로 반응", "correctAnswer": "찬양"}, material)  # 교재에 없음


def test_bad_short_is_repaired_by_regenerating_step2_only(monkeypatch, calls):
    bad = json.loads(GOOD)
    bad["quizzes"][1]["questionText"] = "은혜를 받으면 어떻게 반응하나요?"  # 빈칸 없음
    fixed = {"stepNumber": 2, "questionType": "SHORT", "questionText": "은혜를 받은 사람은 ______로 반응한다.", "correctAnswer": "감사", "explanation": "e"}
    replies = iter([json.dumps(bad), json.dumps(fixed)])
    monkeypatch.setattr(qg, "_complete", lambda p, prompt: calls.append(p) or next(replies))
    out = qg.generate_quizzes(SECTIONS)
    assert calls == ["claude", "claude"]  # 전체 1회 + 2번만 재생성 1회
    assert out["quizzes"][1]["questionText"] == fixed["questionText"]
    assert [q["stepNumber"] for q in out["quizzes"]] == [1, 2, 3]


def test_blank_candidates_from_parenthesized_words():
    secs = [{"type": "point", "number": 1, "title": "(환경)을 붙들면 망한다", "items": [
        {"number": "(1)", "text": "새 (생명)의 길을 여신 (하나님)", "children": [], "notes": []},
        {"number": "(2)", "text": "(관점)이 바뀐다", "children": [], "notes": []}]}]
    # 일반어(하나님)와 제목 단어(관점)는 후보에서 뺀다
    assert qg._blank_candidates(secs, title="믿음과 관점의 변화") == ["환경", "생명"]
    material = qg._build_material_context(secs)
    off = {"questionText": "______이 바뀐다", "correctAnswer": "관점"}
    assert "제목" in qg._cloze_problem(dict(off), material, ["환경", "생명"], "믿음과 관점의 변화")
    assert "후보 밖" in qg._cloze_problem({"questionText": "새 ______의 길", "correctAnswer": "길"}, material, ["환경", "생명"])
    assert qg._cloze_problem({"questionText": "새 ______의 길", "correctAnswer": "생명"}, material, ["환경", "생명"]) is None
