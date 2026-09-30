from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.schemas.partidas import AvancarPergunta, CriarPartida, EnviarResposta, PartidaPublica, ResultadoResposta
from app.security import usuario_atual_opcional
from app.services.partidas import partidas

router = APIRouter()


@router.post("/partidas/{partida_id}/proxima", response_model=PartidaPublica)
def avancar_pergunta(
    partida_id: str,
    entrada: AvancarPergunta,
    db: Session = Depends(get_db),
):
    return partidas.avancar(db, partida_id, entrada.pergunta_id)


@router.post("/partidas", response_model=PartidaPublica, status_code=201)
def criar_partida(
    entrada: CriarPartida,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_atual_opcional),
):
    return partidas.criar(db, entrada.jogador, entrada.categoria, usuario)


@router.post("/partidas/{partida_id}/respostas", response_model=ResultadoResposta)
def enviar_resposta(
    partida_id: str,
    entrada: EnviarResposta,
    db: Session = Depends(get_db),
):
    return partidas.responder(
        db, partida_id, entrada.pergunta_id, entrada.alternativa
    )
