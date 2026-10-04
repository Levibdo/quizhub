from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.perguntas import PERGUNTAS
from app.db.session import get_session_factory
from app.models import Categoria, Pergunta
from app.conteudo import CATEGORIAS_OFICIAIS, MODO_QUIZ_CLASSICO

CATEGORIAS_INICIAIS = (
    {"slug": "geral", "nome": "Geral", "descricao": "Conhecimentos gerais."},
    {
        "slug": "tecnologia",
        "nome": "Tecnologia",
        "descricao": "Fundamentos de tecnologia.",
    },
    {
        "slug": "matematica",
        "nome": "Matemática",
        "descricao": "Conceitos básicos de matemática.",
    },
    {
        "slug": "entretenimento",
        "nome": "Entretenimento",
        "descricao": "Cinema, música, televisão e cultura.",
    },
)


def seed_database(session: Session) -> tuple[int, int]:
    """Insert missing initial records without changing records already present."""
    categorias_criadas = 0
    perguntas_criadas = 0

    with session.begin():
        categorias_existentes = set(session.scalars(select(Categoria.slug).where(
            Categoria.modo == MODO_QUIZ_CLASSICO,
        )))
        for dados in CATEGORIAS_INICIAIS:
            if dados["slug"] not in categorias_existentes:
                session.add(Categoria(
                    id=CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO][dados["slug"]],
                    modo=MODO_QUIZ_CLASSICO,
                    origem="OFICIAL",
                    **dados,
                ))
                categorias_criadas += 1

        perguntas_existentes = set(session.scalars(select(Pergunta.id)))
        criada_em = datetime.now(timezone.utc)
        for pergunta in PERGUNTAS:
            if pergunta.id in perguntas_existentes:
                continue
            session.add(
                Pergunta(
                    id=pergunta.id,
                    categoria_id=CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO][pergunta.categoria],
                    enunciado=pergunta.pergunta,
                    alternativa_a=pergunta.alternativas[0],
                    alternativa_b=pergunta.alternativas[1],
                    alternativa_c=pergunta.alternativas[2],
                    alternativa_d=pergunta.alternativas[3],
                    alternativa_correta=pergunta.correta,
                    explicacao=pergunta.explicacao,
                    criada_em=criada_em,
                )
            )
            perguntas_criadas += 1

    return categorias_criadas, perguntas_criadas


def main() -> None:
    with get_session_factory()() as session:
        categorias, perguntas = seed_database(session)
    print(f"Seed concluído: {categorias} categorias e {perguntas} perguntas criadas.")


if __name__ == "__main__":
    main()
