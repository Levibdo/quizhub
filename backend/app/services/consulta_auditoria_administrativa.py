from datetime import datetime
from math import ceil
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import AuditoriaAdministrativa


def consultar_auditoria_administrativa(
    db: Session,
    *,
    pagina: int,
    limite: int,
    operacao: str | None = None,
    administrador_id: UUID | None = None,
    resultado: str | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    busca: str | None = None,
    ordem: str = "desc",
) -> dict:
    """Consulta somente metadados administrativos, com paginação no SQL."""
    filtros = []
    if operacao:
        filtros.append(AuditoriaAdministrativa.operacao == operacao)
    if administrador_id:
        filtros.append(
            AuditoriaAdministrativa.administrador_id == administrador_id
        )
    if resultado:
        filtros.append(AuditoriaAdministrativa.resultado == resultado)
    if inicio:
        filtros.append(AuditoriaAdministrativa.ocorrida_em >= inicio)
    if fim:
        filtros.append(AuditoriaAdministrativa.ocorrida_em <= fim)
    if busca:
        filtros.append(or_(
            func.lower(AuditoriaAdministrativa.recurso_id).contains(
                busca.casefold(), autoescape=True
            ),
            func.lower(AuditoriaAdministrativa.operacao).contains(
                busca.casefold(), autoescape=True
            ),
            func.lower(AuditoriaAdministrativa.catalogo_id).contains(
                busca.casefold(), autoescape=True
            ),
        ))

    total = db.scalar(
        select(func.count(AuditoriaAdministrativa.id)).where(*filtros)
    ) or 0
    direcao = (
        AuditoriaAdministrativa.ocorrida_em.asc,
        AuditoriaAdministrativa.id.asc,
    ) if ordem == "asc" else (
        AuditoriaAdministrativa.ocorrida_em.desc,
        AuditoriaAdministrativa.id.desc,
    )
    itens = list(db.scalars(
        select(AuditoriaAdministrativa)
        .options(joinedload(AuditoriaAdministrativa.administrador))
        .where(*filtros)
        .order_by(direcao[0](), direcao[1]())
        .offset((pagina - 1) * limite)
        .limit(limite)
    ))
    return {
        "itens": itens,
        "pagina": pagina,
        "limite": limite,
        "total": total,
        "total_paginas": ceil(total / limite) if total else 0,
    }
