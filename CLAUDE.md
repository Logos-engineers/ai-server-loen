# ai-service

Python 3.12 / FastAPI. OBS 교안(PDF 또는 HWP)을 분석해서 sections + summary + quizzes를 생성하는 AI 서비스.
루트 `CLAUDE.md`의 전체 아키텍처 개요를 먼저 참고할 것.

## 역할

백엔드가 R2에 업로드한 PDF/HWP를 받아 규칙 파서로 구조화하고 Claude(실패 시 Gemini)로 퀴즈를 만든 뒤 구조화된 데이터를 반환한다.
외부에 직접 노출되지 않고 백엔드가 중계한다.

## 엔드포인트

```
POST /obs/process
  Request:  { "r2_key": "obs/<uuid>.pdf" | "obs/<uuid>.hwp" }
  Response: { "sections": [...], "summary": [...], "quizzes": [...],
              "meta": { "title", "biblePassage", "publishedDate" },   # 머리말에서 추출, 못 찾으면 null
              "gate": { "templateOk", "missingLines", "warnings" },  # 양식·누락 검사(막지 않고 알림)
              "generator": "claude-opus-5" | "gemini-3.8-flash" }   # 퀴즈를 실제로 만든 모델

GET /health
  Response: { "status": "ok" }
```

## 처리 흐름

```
r2_key 수신 (확장자로 분기)
[.hwp] → pyhwp로 문단 추출 + 자동번호 복원 (hwp_extractor) → 규칙 파서 문단 모드 (refiner 없음)
[.pdf] → pdfplumber 텍스트 추출 (pdf_extractor) → 규칙 파서 → AI 후보정 (section_refiner, 이상 시 초안 폴백)
→ 게이트: 양식 검사 + 원문 누락 줄 검사 (parser.check_gate) · 메타데이터 추출 (parser.extract_meta)
→ summaries + quizzes 생성 (quiz_generator: Claude Opus 5 → 실패 시 Gemini 3.8 flash)
→ { sections, summary, quizzes, meta, gate, generator } 반환
```

> ⚠️ **parser는 LLM이 아니라 정규식 규칙 기반**이다. 특정 OBS 양식("III. 말씀 정리하기",
> "IV. 적용하기", `1.`/`(1)`/`①`/`▶` 등)에 의존한다. 그 뒤 `section_refiner`가 Gemini로
> 구조 오류만 후보정한다(글자는 원문 보존, number는 시스템이 결정적으로 재계산).
> HWP는 문단이 깨끗해 refiner를 쓰지 않는다(PoC에서 8개 중 3개 구조 훼손). 인도자 해설(▶)은
> sections의 notes에 남지만 **퀴즈 생성 입력에서는 뺀다**(참여자가 못 본 정보).

## Sections 스키마

3가지 타입이 순서대로 반환된다: `intro` → `point` (2개 이상) → `application`

### type: intro
```json
{
  "type": "intro",
  "text": "III. 말씀 정리하기 박스의 도입 본문",
  "questions": ["질문1", "질문2"],
  "commentaries": ["▶ 해설1", null]
}
```
- `questions`와 `commentaries`는 같은 길이 배열 (질문에 해설 없으면 null)

### type: point
```json
{
  "type": "point",
  "number": 1,
  "title": "( ) 절기를 지키는 법칙입니다.",
  "answer": "유월절",
  "reference": "출 12:1-14",
  "questions": ["1) 나눔 질문..."],
  "commentaries": ["▶ 인도자 해설..."]
}
```
- `title`의 `( )`는 빈칸 유지
- `answer`: 인도자용 PDF면 채워진 단어, 교재용이면 null

### type: application
```json
{
  "type": "application",
  "text": "IV. 적용하기 질문 전체 텍스트"
}
```

## Quizzes 스키마

AI 모델은 내부적으로 아래 구조를 생성한다:

```json
{
  "summaries": [
    "첫 번째 핵심 요약 문장...",
    "두 번째 핵심 요약 문장...",
    "세 번째 핵심 요약 문장..."
  ],
  "quizzes": [
    {
      "stepNumber": 1,
      "questionType": "OX",
      "questionText": "문제...",
      "correctAnswer": "O",
      "explanation": "해설..."
    },
    {
      "stepNumber": 2,
      "questionType": "SHORT",
      "questionText": "문제...",
      "correctAnswer": "핵심단어",
      "explanation": "해설..."
    },
    {
      "stepNumber": 3,
      "questionType": "ESSAY",
      "questionText": "삶과 믿음에 어떤 영향이 생기나요?",
      "correctAnswer": "은혜 받는 길이 막히고 죄의 열매를 맺게 되어 믿음이 무뎌집니다.",
      "explanation": "인도자 가이드..."
    }
  ]
}
```

라우터 응답에서는 `summaries`를 `summary` 필드로 매핑한다.

`quizzes`는 항상 3개 고정 (stepNumber 1, 2, 3):

```json
[
  {
    "stepNumber": 1,
    "questionType": "OX",
    "questionText": "문제...",
    "correctAnswer": "O",
    "explanation": "해설..."
  },
  {
    "stepNumber": 2,
    "questionType": "SHORT",
    "questionText": "문제...",
    "correctAnswer": "핵심단어",
    "explanation": "해설..."
  },
  {
    "stepNumber": 3,
    "questionType": "ESSAY",
    "questionText": "삶과 믿음에 어떤 영향이 생기나요?",
    "correctAnswer": "은혜 받는 길이 막히고 죄의 열매를 맺게 되어 믿음이 무뎌집니다.",
    "explanation": "인도자 가이드..."
  }
]
```

`summary`는 항상 3줄을 기대한다.
백엔드 `ObsQuiz` entity의 `questionType` 필드에 그대로 저장됨 (String 타입).

## R2 Client

`services/r2_client.py`가 boto3로 Cloudflare R2에 연결한다.
```python
download_file(key: str) -> bytes
upload_file(key: str, data: bytes, content_type: str) -> str
delete_file(key: str)
```

## AI 모델

- 파서(parser): **LLM 아님 — 정규식 규칙 기반** sections 구조화
- 후보정(section_refiner, PDF만): `gemini-2.5-flash-lite` — 규칙 파서 초안의 구조 오류(텍스트 끊김·계층)만 교정. 내용이 30% 넘게 줄거나 늘면, 또는 intro에 머리말이 끼면 초안 폴백
- 요약/퀴즈 생성·문제 재생성(quiz_generator): `claude-opus-5` 기본 → 실패 시 `gemini-3.8-flash`.
  - 폴백 조건: API 오류(크레딧·인증·5xx·연결, SDK 재시도 후) → 즉시 다음 공급자 / JSON·형식 불일치 → 같은 공급자 재시도 후 다음
  - Claude 안전 거절은 서버 측 폴백(`fallbacks="default"`, beta `server-side-fallback-2026-07-01`)이 먼저 처리
  - `ANTHROPIC_API_KEY`가 없거나 `QUIZ_PROVIDER=gemini`면 Gemini만 사용
  - 모델 선택 근거: 루트 `docs/obs-quiz-model-comparison.html`

## Environment Variables

`ai-service/.env` 생성 필요:
```
GEMINI_API_KEY=
CLOUDFLARE_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
INTERNAL_API_TOKEN=   # 백엔드 중계 인증용 공유 시크릿 (백엔드 AI_INTERNAL_TOKEN과 동일 값). 미설정 시 /obs/process 503 거부
ENABLE_SECTION_REFINE=true   # (선택) sections AI 후보정 on/off. 기본 켜짐, 끄려면 false (kill switch)
ANTHROPIC_API_KEY=           # 퀴즈 생성 Claude 키. 없으면 Gemini만 사용
QUIZ_PROVIDER=claude         # (선택) claude(기본) | gemini — 비상시 Claude 끄기
```

> ⚠️ `/obs/process`는 `X-Internal-Token` 헤더가 `INTERNAL_API_TOKEN`과 일치해야만 동작한다(내부 전용).
> 토큰 미설정이면 fail-closed로 503을 반환한다 — 로컬·운영 모두 반드시 설정할 것.

## Run

```bash
cd ai-service
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Docker
docker build -t loen-ai .
docker run -p 8000:8000 --env-file .env loen-ai
```

## File Structure

```
main.py              # FastAPI app, /obs 라우터 등록
routers/obs.py       # POST /obs/process 엔드포인트
services/
  pdf_extractor.py    # R2 다운로드 + pdfplumber 텍스트 추출
  hwp_extractor.py    # pyhwp로 HWP 문단 추출 + 자동번호 복원
  parser.py           # 규칙(정규식) 기반 sections 구조화 (LLM 아님) + 메타데이터 + 게이트
  section_refiner.py  # Gemini로 sections 구조 오류 후보정 (PDF만, 이상 시 초안 폴백)
  quiz_generator.py   # Claude(→Gemini 폴백)로 summaries + quizzes 생성·재생성
tests/                # pytest (pip install pytest httpx). 실제 HWP 골든 테스트: OBS_HWP_DIR=<폴더> pytest tests
  r2_client.py        # boto3 R2 클라이언트
```
