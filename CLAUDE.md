# ai-service

Python 3.12 / FastAPI. OBS PDF를 분석해서 sections + summary + quizzes를 생성하는 AI 서비스.
루트 `CLAUDE.md`의 전체 아키텍처 개요를 먼저 참고할 것.

## 역할

백엔드가 R2에 업로드한 PDF를 받아 Gemini로 분석 후 구조화된 데이터를 반환한다.
외부에 직접 노출되지 않고 백엔드가 중계한다.

## 엔드포인트

```
POST /obs/process
  Request:  { "r2_key": "obs/<uuid>.pdf" }
  Response: { "sections": [...], "summary": [...], "quizzes": [...] }

GET /health
  Response: { "status": "ok" }
```

## 처리 흐름

```
r2_key 수신
→ R2에서 PDF 바이트 다운로드 (r2_client.download_file)
→ pdfplumber로 텍스트 추출 (pdf_extractor)
→ Gemini로 sections 파싱 (parser)
→ Gemini로 summaries + quizzes 생성 (quiz_generator)
→ { sections, summary, quizzes } 반환
```

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

- 파서: `gemini-2.5-flash` (sections 구조화)
- 요약/퀴즈 생성: `gemini-2.5-flash` (3줄 요약 + 3개 퀴즈 생성)
- 두 호출 모두 JSON 파싱 실패 시 1회 재시도

## Environment Variables

`ai-service/.env` 생성 필요:
```
GEMINI_API_KEY=
CLOUDFLARE_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
```

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
  pdf_extractor.py   # R2 다운로드 + pdfplumber 텍스트 추출
  parser.py          # Gemini로 sections 파싱
  quiz_generator.py  # Gemini로 summaries + quizzes 생성
  r2_client.py       # boto3 R2 클라이언트
```
