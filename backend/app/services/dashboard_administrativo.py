from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    AuditoriaAdministrativa,
    CatalogoOficial,
    Categoria,
    Partida,
    PartidaNemPato,
    Pergunta,
    PerguntaNemPato,
    Temporada,
    Usuario,
)


def _contagem_usuarios(db: Session) -> dict[str, int]:
    total, ativos = db.execute(select(
        func.count(Usuario.id),
        func.count(Usuario.id).filter(Usuario.ativo.is_(True)),
    )).one()
    return {"total": total, "ativos": ativos}


def _contagem_origem(db: Session, modelo) -> dict[str, int]:
    filtros = []
    if hasattr(modelo, "excluida_em"):
        filtros.append(modelo.excluida_em.is_(None))
    total, oficiais, privadas = db.execute(
        select(
            func.count(modelo.id),
            func.count(modelo.id).filter(modelo.origem == "OFICIAL"),
            func.count(modelo.id).filter(modelo.origem == "USUARIO"),
        ).where(*filtros)
    ).one()
    return {"total": total, "oficiais": oficiais, "privadas": privadas}


def _somar_origens(*contagens: dict[str, int]) -> dict[str, int]:
    return {
        campo: sum(contagem[campo] for contagem in contagens)
        for campo in ("total", "oficiais", "privadas")
    }


def _contagem_partidas(db: Session, modelo) -> dict[str, int]:
    total, concluidas = db.execute(select(
        func.count(modelo.id),
        func.count(modelo.id).filter(modelo.status == "FINALIZADA"),
    )).one()
    return {"total": total, "concluidas": concluidas}


def obter_dashboard_administrativo(
    db: Session, *, limite_auditoria: int
) -> dict:
    quiz_classico = _contagem_partidas(db, Partida)
    nem_a_pato = _contagem_partidas(db, PartidaNemPato)
    perguntas = _somar_origens(
        _contagem_origem(db, Pergunta),
        _contagem_origem(db, PerguntaNemPato),
    )
    categorias = _contagem_origem(db, Categoria)
    catalogos = list(db.scalars(
        select(CatalogoOficial).order_by(
            CatalogoOficial.modo,
            CatalogoOficial.versao.desc(),
        )
    ))
    auditorias = list(db.scalars(
        select(AuditoriaAdministrativa)
        .options(joinedload(AuditoriaAdministrativa.administrador))
        .order_by(AuditoriaAdministrativa.ocorrida_em.desc())
        .limit(limite_auditoria)
    ))
    temporada_ativa = db.scalar(
        select(Temporada).where(Temporada.status == "ATIVA")
    )
    return {
        "indicadores": {
            "usuarios": _contagem_usuarios(db),
            "partidas": {
                "total": quiz_classico["total"] + nem_a_pato["total"],
                "concluidas": (
                    quiz_classico["concluidas"] + nem_a_pato["concluidas"]
                ),
                "quiz_classico": quiz_classico,
                "nem_a_pato": nem_a_pato,
            },
            "perguntas": perguntas,
            "categorias": categorias,
            "catalogos_oficiais_ativos": sum(
                item.status == "ATIVO" for item in catalogos
            ),
        },
        "catalogos": catalogos,
        "auditorias": auditorias,
        "temporada_ativa": temporada_ativa,
    }
