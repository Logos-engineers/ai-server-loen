from fastapi import FastAPI
from routers import obs

app = FastAPI(title="Loen AI Service")

app.include_router(obs.router, prefix="/obs", tags=["obs"])


@app.get("/health")
def health():
    return {"status": "ok"}
