from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import AuditoriaAdministrativa, CatalogoOficial, Usuario
from app.schemas.admin import (
    AuditoriaAdministrativaPublica,
    CatalogoAdministrativo,
    ResumoAdministrativo,
)
from app.security import exigir_admin


router = APIRouter(prefix="/admin", tags=["Administração"])


@router.get("/resumo", response_model=ResumoAdministrativo)
def resumo_administrativo(
    limite_auditoria: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    catalogos = list(
        db.scalars(
            select(CatalogoOficial).order_by(
                CatalogoOficial.modo,
                CatalogoOficial.versao.desc(),
            )
        )
    )
    auditorias = list(
        db.scalars(
            select(AuditoriaAdministrativa)
            .options(joinedload(AuditoriaAdministrativa.administrador))
            .order_by(AuditoriaAdministrativa.ocorrida_em.desc())
            .limit(limite_auditoria)
        )
    )
    return ResumoAdministrativo(
        catalogos=[CatalogoAdministrativo.model_validate(item) for item in catalogos],
        auditorias=[
            AuditoriaAdministrativaPublica(
                id=item.id,
                administrador_id=item.administrador_id,
                administrador_nome=item.administrador.nome,
                ocorrida_em=item.ocorrida_em,
                operacao=item.operacao,
                recurso_tipo=item.recurso_tipo,
                recurso_id=item.recurso_id,
                resultado=item.resultado,
                catalogo_id=item.catalogo_id,
                catalogo_versao=item.catalogo_versao,
                detalhes=item.detalhes,
            )
            for item in auditorias
        ],
    )
