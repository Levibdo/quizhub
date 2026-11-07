from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.schemas.partidas import (
    AvancarPergunta,
    CriarPartida,
    EnviarResposta,
    PartidaPublica,
    PartidaRecuperada,
    ResultadoResposta,
)
from app.security import (
    CLASSIC_GUEST_COOKIE_NAME,
    CLASSIC_GUEST_DURATION,
    cookie_secure,
    criar_token_visitante_classico,
    exigir_origem_confiavel,
    identificar_visitante_classico,
    usuario_atual_opcional,
)
from app.services.partidas import partidas

router = APIRouter()


def _identidade_partida(
    usuario: Usuario | None,
    token_visitante: str | None,
):
    visitante_id = identificar_visitante_classico(token_visitante)
    if usuario is None and visitante_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="identidade da partida ausente ou expirada",
        )
    return visitante_id


@router.post("/partidas/{partida_id}/proxima", response_model=PartidaPublica)
def avancar_pergunta(
    partida_id: str,
    entrada: AvancarPergunta,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_atual_opcional),
    token_visitante: str | None = Cookie(
        default=None, alias=CLASSIC_GUEST_COOKIE_NAME
    ),
    _origem: None = Depends(exigir_origem_confiavel),
):
    return partidas.avancar(
        db,
        partida_id,
        entrada.pergunta_id,
        usuario,
        _identidade_partida(usuario, token_visitante),
    )


@router.get("/partidas/{partida_id}", response_model=PartidaRecuperada)
def recuperar_partida(
    partida_id: str,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_atual_opcional),
    token_visitante: str | None = Cookie(
        default=None, alias=CLASSIC_GUEST_COOKIE_NAME
    ),
):
    return partidas.recuperar(
        db,
        partida_id,
        usuario,
        _identidade_partida(usuario, token_visitante),
    )


@router.post("/partidas", response_model=PartidaPublica, status_code=201)
def criar_partida(
    entrada: CriarPartida,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_atual_opcional),
    token_visitante: str | None = Cookie(
        default=None, alias=CLASSIC_GUEST_COOKIE_NAME
    ),
    _origem: None = Depends(exigir_origem_confiavel),
):
    visitante_id = None
    if usuario is None:
        visitante_id = identificar_visitante_classico(token_visitante)
        if visitante_id is None:
            visitante_id = uuid4()
            response.set_cookie(
                key=CLASSIC_GUEST_COOKIE_NAME,
                value=criar_token_visitante_classico(visitante_id),
                max_age=int(CLASSIC_GUEST_DURATION.total_seconds()),
                httponly=True,
                secure=cookie_secure(),
                samesite="lax",
                path="/api/v1/partidas",
            )
    return partidas.criar(
        db,
        entrada.jogador,
        entrada.categoria,
        usuario,
        visitante_id=visitante_id,
    )


@router.post("/partidas/{partida_id}/respostas", response_model=ResultadoResposta)
def enviar_resposta(
    partida_id: str,
    entrada: EnviarResposta,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_atual_opcional),
    token_visitante: str | None = Cookie(
        default=None, alias=CLASSIC_GUEST_COOKIE_NAME
    ),
    _origem: None = Depends(exigir_origem_confiavel),
):
    return partidas.responder(
        db,
        partida_id,
        entrada.pergunta_id,
        entrada.alternativa,
        usuario,
        _identidade_partida(usuario, token_visitante),
    )
