from math import ceil
from uuid import UUID

from sqlalchemy import String, cast, func, literal, select, union_all
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import CatalogoOficial, Categoria, Pergunta, PerguntaNemPato


def _selecao_quiz():
    return (
        select(
            Pergunta.id.label("id"),
            Pergunta.id_editorial.label("id_editorial"),
            literal("QUIZ_CLASSICO").label("modo"),
            Pergunta.enunciado.label("enunciado"),
            Pergunta.ativa.label("ativa"),
            Pergunta.dificuldade.label("dificuldade"),
            Categoria.id.label("categoria_id"),
            Categoria.slug.label("categoria_slug"),
            Categoria.nome.label("categoria_nome"),
            CatalogoOficial.id.label("catalogo_uuid"),
            CatalogoOficial.catalogo_id.label("catalogo_id"),
            CatalogoOficial.versao.label("catalogo_versao"),
            CatalogoOficial.status.label("catalogo_status"),
        )
        .join(Categoria, Categoria.id == Pergunta.categoria_id)
        .join(CatalogoOficial, CatalogoOficial.id == Pergunta.catalogo_oficial_id)
        .where(
            Pergunta.origem == "OFICIAL",
            Categoria.origem == "OFICIAL",
            CatalogoOficial.modo == "QUIZ_CLASSICO",
        )
    )


def _selecao_nem_pato():
    return (
        select(
            PerguntaNemPato.id.label("id"),
            PerguntaNemPato.id_editorial.label("id_editorial"),
            literal("NEM_A_PATO").label("modo"),
            PerguntaNemPato.enunciado.label("enunciado"),
            PerguntaNemPato.ativa.label("ativa"),
            cast(literal(None), String(8)).label("dificuldade"),
            Categoria.id.label("categoria_id"),
            Categoria.slug.label("categoria_slug"),
            Categoria.nome.label("categoria_nome"),
            CatalogoOficial.id.label("catalogo_uuid"),
            CatalogoOficial.catalogo_id.label("catalogo_id"),
            CatalogoOficial.versao.label("catalogo_versao"),
            CatalogoOficial.status.label("catalogo_status"),
        )
        .join(Categoria, Categoria.id == PerguntaNemPato.categoria_id)
        .join(
            CatalogoOficial,
            CatalogoOficial.id == PerguntaNemPato.catalogo_oficial_id,
        )
        .where(
            PerguntaNemPato.origem == "OFICIAL",
            Categoria.origem == "OFICIAL",
            CatalogoOficial.modo == "NEM_A_PATO",
        )
    )


def consultar_perguntas_oficiais(
    db: Session,
    *,
    pagina: int,
    limite: int,
    modo: str | None = None,
    catalogo_id: UUID | None = None,
    versao: int | None = None,
    categoria_id: UUID | None = None,
    ativa: bool | None = None,
    dificuldade: str | None = None,
    busca: str | None = None,
) -> dict:
    """Une os dois modos e pagina integralmente no banco de dados."""
    selecoes = []
    if modo in (None, "QUIZ_CLASSICO"):
        selecoes.append(_selecao_quiz())
    if modo in (None, "NEM_A_PATO") and dificuldade is None:
        selecoes.append(_selecao_nem_pato())
    if not selecoes:
        return {
            "itens": [], "pagina": pagina, "limite": limite,
            "total": 0, "total_paginas": 0,
        }

    uniao = union_all(*selecoes).subquery("perguntas_oficiais")
    filtros = []
    if catalogo_id:
        filtros.append(uniao.c.catalogo_uuid == catalogo_id)
    if versao is not None:
        filtros.append(uniao.c.catalogo_versao == versao)
    if categoria_id:
        filtros.append(uniao.c.categoria_id == categoria_id)
    if ativa is not None:
        filtros.append(uniao.c.ativa == ativa)
    if dificuldade:
        filtros.append(uniao.c.dificuldade == dificuldade)
    if busca:
        filtros.append(func.lower(uniao.c.enunciado).contains(
            busca.casefold(), autoescape=True,
        ))

    total = db.scalar(select(func.count()).select_from(uniao).where(*filtros)) or 0
    linhas = db.execute(
        select(uniao)
        .where(*filtros)
        .order_by(
            uniao.c.modo.asc(),
            uniao.c.catalogo_id.asc(),
            uniao.c.catalogo_versao.desc(),
            uniao.c.id.asc(),
        )
        .offset((pagina - 1) * limite)
        .limit(limite)
    ).mappings().all()
    itens = [
        {
            "id": linha["id"],
            "id_editorial": linha["id_editorial"],
            "modo": linha["modo"],
            "enunciado": linha["enunciado"],
            "ativa": linha["ativa"],
            "dificuldade": linha["dificuldade"],
            "categoria": {
                "id": linha["categoria_id"],
                "slug": linha["categoria_slug"],
                "nome": linha["categoria_nome"],
            },
            "catalogo": {
                "id": linha["catalogo_uuid"],
                "catalogo_id": linha["catalogo_id"],
                "versao": linha["catalogo_versao"],
                "status": linha["catalogo_status"],
            },
        }
        for linha in linhas
    ]
    return {
        "itens": itens,
        "pagina": pagina,
        "limite": limite,
        "total": total,
        "total_paginas": ceil(total / limite) if total else 0,
    }


def opcoes_perguntas_oficiais(db: Session) -> dict:
    catalogos = list(db.scalars(
        select(CatalogoOficial).order_by(
            CatalogoOficial.modo,
            CatalogoOficial.catalogo_id,
            CatalogoOficial.versao.desc(),
        )
    ))
    categorias = list(db.scalars(
        select(Categoria)
        .where(Categoria.origem == "OFICIAL")
        .order_by(Categoria.modo, Categoria.nome, Categoria.id)
    ))
    return {
        "catalogos": [
            {
                "id": item.id, "catalogo_id": item.catalogo_id,
                "versao": item.versao, "status": item.status, "modo": item.modo,
            }
            for item in catalogos
        ],
        "categorias": [
            {
                "id": item.id, "slug": item.slug,
                "nome": item.nome, "modo": item.modo,
            }
            for item in categorias
        ],
    }


def obter_pergunta_oficial(db: Session, *, modo: str, pergunta_id: int) -> dict | None:
    if modo == "QUIZ_CLASSICO":
        pergunta = db.scalar(
            select(Pergunta)
            .join(Pergunta.categoria)
            .join(Pergunta.catalogo_oficial)
            .options(
                joinedload(Pergunta.categoria),
                joinedload(Pergunta.catalogo_oficial),
                selectinload(Pergunta.fontes_editoriais),
            )
            .where(
                Pergunta.id == pergunta_id,
                Pergunta.origem == "OFICIAL",
                Categoria.origem == "OFICIAL",
            )
        )
        if pergunta is None:
            return None
        alternativas = [
            pergunta.alternativa_a, pergunta.alternativa_b,
            pergunta.alternativa_c, pergunta.alternativa_d,
        ]
        resposta_numerica = None
        unidade = tema = natureza = qualificacao = fonte_legada = None
    else:
        pergunta = db.scalar(
            select(PerguntaNemPato)
            .join(PerguntaNemPato.categoria)
            .join(PerguntaNemPato.catalogo_oficial)
            .options(
                joinedload(PerguntaNemPato.categoria),
                joinedload(PerguntaNemPato.catalogo_oficial),
                selectinload(PerguntaNemPato.fontes_editoriais),
            )
            .where(
                PerguntaNemPato.id == pergunta_id,
                PerguntaNemPato.origem == "OFICIAL",
                Categoria.origem == "OFICIAL",
            )
        )
        if pergunta is None:
            return None
        alternativas = None
        resposta_numerica = str(pergunta.resposta_numerica)
        unidade = pergunta.unidade
        tema = pergunta.tema_editorial
        natureza = pergunta.natureza_resposta
        qualificacao = pergunta.qualificacao_estimativa
        fonte_legada = {
            "nome": pergunta.fonte,
            "url": pergunta.fonte_url,
            "acessada_em": pergunta.fonte_acessada_em,
        } if any((pergunta.fonte, pergunta.fonte_url, pergunta.fonte_acessada_em)) else None

    catalogo = pergunta.catalogo_oficial
    return {
        "id": pergunta.id,
        "id_editorial": pergunta.id_editorial,
        "modo": modo,
        "enunciado": pergunta.enunciado,
        "ativa": pergunta.ativa,
        "dificuldade": getattr(pergunta, "dificuldade", None),
        "categoria": {
            "id": pergunta.categoria.id,
            "slug": pergunta.categoria.slug,
            "nome": pergunta.categoria.nome,
        },
        "catalogo": {
            "id": catalogo.id,
            "catalogo_id": catalogo.catalogo_id,
            "versao": catalogo.versao,
            "status": catalogo.status,
        },
        "explicacao": pergunta.explicacao,
        "alternativas": alternativas,
        "alternativa_correta": getattr(pergunta, "alternativa_correta", None),
        "resposta_numerica": resposta_numerica,
        "unidade": unidade,
        "tema_editorial": tema,
        "natureza_resposta": natureza,
        "qualificacao_estimativa": qualificacao,
        "fonte_legada": fonte_legada,
        "referencias": [
            {
                "titulo": fonte.titulo,
                "url": fonte.url,
                "acessada_em": fonte.acessada_em,
            }
            for fonte in pergunta.fontes_editoriais
        ],
    }
