import os
import sys

# 서비스 모듈은 import 시점에 genai.configure()/boto3.client()를 실행한다 — 네트워크 호출은 없어 더미로 충분.
for k in ("GEMINI_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
    os.environ.setdefault(k, "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
