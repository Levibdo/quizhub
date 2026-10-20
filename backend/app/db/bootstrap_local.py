"""Inicializa os catálogos canônicos somente em bancos locais autorizados."""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

from app.db.session import get_database_url, get_session_factory
from app.services.catalogos_oficiais import catalogos_oficiais_service


RAIZ_BACKEND = Path(__file__).resolve().parents[2]
CATALOGO_QUIZ = RAIZ_BACKEND / "dados_oficiais" / "quiz_classico_v2.json"
CATALOGO_NEM_PATO = (
    RAIZ_BACKEND / "dados_oficiais" / "nem_a_pato_macabro_v1.json"
)


def _permitido() -> bool:
    ambiente = os.getenv("QUIZHUB_LOCAL_ENVIRONMENT", "").strip().casefold()
    habilitado = os.getenv(
        "QUIZHUB_BOOTSTRAP_OFFICIAL_CATALOGS", ""
    ).strip().casefold()
    return ambiente == "development" and habilitado in {"1", "true", "yes"}


def _validar_banco_local() -> str:
    if not _permitido():
        raise RuntimeError(
            "bootstrap local recusado: habilite explicitamente o ambiente de desenvolvimento"
        )
    nome = make_url(get_database_url()).database or ""
    if not nome.startswith("quizhub_local"):
        raise RuntimeError(
            "bootstrap local recusado: o banco deve usar o prefixo 'quizhub_local'"
        )
    return nome


def carregar_catalogos_locais() -> tuple[int, int]:
    """Prepara e ativa os dois catálogos canônicos de forma transacional."""
    _validar_banco_local()
    with get_session_factory()() as session, session.begin():
        quiz = catalogos_oficiais_service.preparar_quiz(session, CATALOGO_QUIZ)
        catalogos_oficiais_service.ativar(
            session, quiz.catalogo_id, quiz.versao
        )
        nem_pato = catalogos_oficiais_service.preparar_nem_pato(
            session, CATALOGO_NEM_PATO
        )
        catalogos_oficiais_service.ativar(
            session, nem_pato.catalogo_id, nem_pato.versao
        )
    return quiz.criadas, nem_pato.criadas


def main() -> None:
    quiz, nem_pato = carregar_catalogos_locais()
    print(
        "Catálogos locais prontos: "
        f"{quiz} perguntas novas do Quiz Clássico e "
        f"{nem_pato} perguntas novas do Nem a Pato."
    )


if __name__ == "__main__":
    main()
