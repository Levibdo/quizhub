from pathlib import Path

from dotenv import load_dotenv

ARQUIVO_ENV = Path(__file__).resolve().parents[1] / ".env"


def carregar_variaveis_ambiente(caminho: Path = ARQUIVO_ENV) -> None:
    load_dotenv(dotenv_path=caminho, override=False)


carregar_variaveis_ambiente()
