"""Infraestrutura comum para testes operacionais na revisão Alembic atual."""

from sqlalchemy import select

from app.models import CatalogoOficial


def garantir_catalogo_ativo(db, modo: str):
    catalogo = db.scalar(
        select(CatalogoOficial).where(
            CatalogoOficial.modo == modo,
            CatalogoOficial.status == "ATIVO",
        )
    )
    if catalogo is not None:
        return catalogo

    catalogo = CatalogoOficial(
        catalogo_id=f"integracao-{modo.lower().replace('_', '-')}",
        versao=1,
        modo=modo,
        status="ATIVO",
        sha256="0" * 64,
    )
    db.add(catalogo)
    db.flush()
    return catalogo
