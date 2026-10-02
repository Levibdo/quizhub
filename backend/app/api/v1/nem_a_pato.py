from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.nem_a_pato import (
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


@router.post("/{codigo}/abandonar", response_model=SalaLobbyPublica)
def abandonar_sala(
    codigo: str,
    token: str | None = Header(default=None, alias=HEADER_TOKEN_NEM_PATO),
    db: Session = Depends(get_db),
):
    return salas_nem_a_pato.abandonar(db, codigo, token)