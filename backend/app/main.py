import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router

app = FastAPI(
    title="QuizHub API",
    version="1.0.0",
)

origens_configuradas = [
    origem.strip()
    for origem in os.getenv("CORS_ORIGINS", "").split(",")
    if origem.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origens_configuradas,
    allow_origin_regex=(
        r"^https?://(?:localhost|127\.0\.0\.1|"
        r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}|"
        r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?):5173$"
    ),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)


@app.get("/")
def raiz():
    return {
        "mensagem": "API do QuizHub funcionando"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


app.include_router(api_router)
