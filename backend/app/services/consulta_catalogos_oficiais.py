from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import CatalogoOficial, Categoria, Pergunta, PerguntaNemPato


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
    maior_categoria_quiz = (
        select(func.count(Pergunta.id))
        .join(Categoria, Categoria.id == Pergunta.categoria_id)
        .where(
            Pergunta.catalogo_oficial_id == CatalogoOficial.id,
            Pergunta.origem == "OFICIAL", Pergunta.usuario_id.is_(None),
            Pergunta.ativa.is_(True), Pergunta.excluida_em.is_(None),
            Pergunta.fontes_editoriais.any(), Categoria.modo == "QUIZ_CLASSICO",
            Categoria.origem == "OFICIAL", Categoria.usuario_id.is_(None),
            Categoria.ativa.is_(True), Categoria.excluida_em.is_(None),
        )
        .group_by(Categoria.id).order_by(func.count(Pergunta.id).desc()).limit(1)
        .correlate(CatalogoOficial).scalar_subquery()
    )
    elegiveis_nem_pato = (
        select(func.count(PerguntaNemPato.id)).join(Categoria)
        .where(
            PerguntaNemPato.catalogo_oficial_id == CatalogoOficial.id,
            PerguntaNemPato.origem == "OFICIAL", PerguntaNemPato.usuario_id.is_(None),
            PerguntaNemPato.ativa.is_(True), PerguntaNemPato.excluida_em.is_(None),
            PerguntaNemPato.fontes_editoriais.any(), Categoria.modo == "NEM_A_PATO",
            Categoria.origem == "OFICIAL", Categoria.usuario_id.is_(None),
            Categoria.ativa.is_(True), Categoria.excluida_em.is_(None),
        ).correlate(CatalogoOficial).scalar_subquery()
    )
    elegiveis = case(
        (CatalogoOficial.modo == "QUIZ_CLASSICO", func.coalesce(maior_categoria_quiz, 0)),
        else_=elegiveis_nem_pato,
    ).label("quantidade_elegivel_reativacao")
    registros = db.execute(
        select(CatalogoOficial, quantidade, elegiveis).order_by(
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
            "quantidade_elegivel_reativacao": quantidade_elegivel,
            "elegivel_reativacao": catalogo.status == "ARQUIVADO" and quantidade_elegivel >= 10,
        }
        for catalogo, quantidade_perguntas, quantidade_elegivel in registros
    ]
