from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import CatalogoOficial, Pergunta, PerguntaNemPato


def consultar_catalogos_oficiais(db: Session) -> list[dict]:
    """Lista versões oficiais e conta suas perguntas em uma única consulta."""
    perguntas_quiz = (
        select(func.count(Pergunta.id))
        .where(Pergunta.catalogo_oficial_id == CatalogoOficial.id)
        .correlate(CatalogoOficial)
        .scalar_subquery()
    )
    perguntas_nem_pato = (
        select(func.count(PerguntaNemPato.id))
        .where(PerguntaNemPato.catalogo_oficial_id == CatalogoOficial.id)
        .correlate(CatalogoOficial)
        .scalar_subquery()
    )
    quantidade = case(
        (CatalogoOficial.modo == "QUIZ_CLASSICO", perguntas_quiz),
        else_=perguntas_nem_pato,
    ).label("quantidade_perguntas")
    registros = db.execute(
        select(CatalogoOficial, quantidade).order_by(
            CatalogoOficial.modo,
            CatalogoOficial.versao.desc(),
            CatalogoOficial.id,
        )
    ).all()
    return [
        {
            "id": catalogo.id,
            "catalogo_id": catalogo.catalogo_id,
            "modo": catalogo.modo,
            "versao": catalogo.versao,
            "status_registro": catalogo.status,
            # O modelo atual não mantém um estado editorial independente.
            "estado_editorial": None,
            "situacao_ativacao": (
                "ATIVO" if catalogo.status == "ATIVO" else "INATIVO"
            ),
            "quantidade_perguntas": quantidade_perguntas,
            "criado_em": catalogo.criado_em,
            "ativado_em": catalogo.ativado_em,
            "arquivado_em": catalogo.arquivado_em,
        }
        for catalogo, quantidade_perguntas in registros
    ]
