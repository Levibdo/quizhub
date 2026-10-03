from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.nem_a_pato import (
    CriarDesafioNemPato,
    CriarPalpiteNemPato,
    CriarSalaNemAPato,
    EntrarSalaNemAPato,
    ParticipacaoSalaCriada,
    SalaLobbyPublica,
    SalaRecuperada,
)
from app.services.salas_nem_a_pato import HEADER_TOKEN_NEM_PATO, salas_nem_a_pato

router = APIRouter(prefix="/nem-pato/salas", tags=["nem-pato"])


@router.post(
    "",
    response_model=ParticipacaoSalaCriada,
    status_code=status.HTTP_201_CREATED,
)
def criar_sala(
    entrada: CriarSalaNemAPato,
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.criar(db, entrada.nome)


@router.post(
    "/{codigo}/participantes",
    response_model=ParticipacaoSalaCriada,
    status_code=status.HTTP_201_CREATED,
)
def entrar_na_sala(
    codigo: str,
    entrada: EntrarSalaNemAPato,
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.entrar(db, codigo, entrada.nome)


@router.get("/{codigo}", response_model=SalaLobbyPublica)
def estado_da_sala(codigo: str, db: Session = Depends(get_db)):
    return salas_nem_a_pato.estado_publico(db, codigo)


@router.get("/{codigo}/eu", response_model=SalaRecuperada)
def recuperar_participacao(
    codigo: str,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.recuperar(db, codigo, token)


@router.post("/{codigo}/iniciar", response_model=SalaRecuperada)
def iniciar_partida(
    codigo: str,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.iniciar(db, codigo, token)


@router.post("/{codigo}/rodadas/iniciar", response_model=SalaRecuperada)
def iniciar_rodada(
    codigo: str,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.iniciar_rodada(db, codigo, token)


@router.post(
    "/{codigo}/rodadas/{rodada_id}/palpites",
    response_model=SalaRecuperada,
)
def criar_palpite(
    codigo: str,
    rodada_id: int,
    entrada: CriarPalpiteNemPato,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.palpitar(
        db,
        codigo,
        rodada_id,
        token,
        entrada.valor,
        entrada.client_action_id,
    )


@router.post(
    "/{codigo}/rodadas/{rodada_id}/desafiar",
    response_model=SalaRecuperada,
)
def desafiar_palpite(
    codigo: str,
    rodada_id: int,
    entrada: CriarDesafioNemPato,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.desafiar(
        db, codigo, rodada_id, token, entrada.client_action_id
    )


@router.post(
    "/{codigo}/rodadas/{rodada_id}/proxima",
    response_model=SalaRecuperada,
)
def iniciar_proxima_rodada(
    codigo: str,
    rodada_id: int,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.iniciar_proxima_rodada(
        db, codigo, rodada_id, token
    )


@router.post("/{codigo}/abandonar", response_model=SalaLobbyPublica)
def abandonar_sala(
    codigo: str,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.abandonar(db, codigo, token)
