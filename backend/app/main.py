from fastapi import FastAPI

from app.api.v1 import api_router

app = FastAPI(
    title="QuizHub API",
    version="1.0.0",
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