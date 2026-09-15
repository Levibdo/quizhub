from fastapi import FastAPI

app = FastAPI(
    title="Quiz Estágio API",
    version="1.0.0",
)


@app.get("/")
def raiz():
    return {
        "mensagem": "API do Quiz Estágio funcionando"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }