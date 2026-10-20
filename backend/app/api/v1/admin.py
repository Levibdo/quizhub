from fastapi import APIRouter, Cookie, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import AuditoriaAdministrativa, CatalogoOficial, Usuario
from app.schemas.admin import (
    AuditoriaAdministrativaPublica,
    CatalogoAdministrativo,
    DashboardAdministrativo,
    ResumoAdministrativo,
    TokenCsrfAdministrativo,
)
from app.services.dashboard_administrativo import obter_dashboard_administrativo
from app.services.seguranca_administrativa import sanitizar_detalhes_auditoria
from app.security import (
    CSRF_COOKIE_NAME,
    CSRF_DURACAO,
    JWT_COOKIE_NAME,
    cookie_secure,
    criar_token_csrf,
    exigir_admin,
)


router = APIRouter(prefix="/admin", tags=["Administração"])


def _serializar_auditoria(item) -> AuditoriaAdministrativaPublica:
    return AuditoriaAdministrativaPublica(
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
        detalhes=sanitizar_detalhes_auditoria(item.detalhes),
    )


@router.get("/csrf", response_model=TokenCsrfAdministrativo)
def emitir_token_csrf_administrativo(
    response: Response,
    token_sessao: str = Cookie(alias=JWT_COOKIE_NAME),
    administrador: Usuario = Depends(exigir_admin),
):
    token = criar_token_csrf(administrador.id, token_sessao)
    duracao = int(CSRF_DURACAO.total_seconds())
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=duracao,
        httponly=False,
        secure=cookie_secure(),
        samesite="strict",
        path="/api/v1",
    )
    return TokenCsrfAdministrativo(token=token, expira_em_segundos=duracao)


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
        auditorias=[_serializar_auditoria(item) for item in auditorias],
    )


def _serializar_dashboard(dados: dict) -> DashboardAdministrativo:
    return DashboardAdministrativo(
        indicadores=dados["indicadores"],
        temporada_ativa=dados["temporada_ativa"],
        catalogos=[
            CatalogoAdministrativo.model_validate(item)
            for item in dados["catalogos"]
        ],
        auditorias=[
            _serializar_auditoria(item) for item in dados["auditorias"]
        ],
    )


@router.get("/dashboard", response_model=DashboardAdministrativo)
def dashboard_administrativo(
    limite_auditoria: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    return _serializar_dashboard(obter_dashboard_administrativo(
        db, limite_auditoria=limite_auditoria
    ))
