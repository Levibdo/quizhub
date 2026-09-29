from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.partidas import CriarPartida, EnviarResposta, PartidaPublica, ResultadoResposta
from app.services.partidas import partidas

router = APIRouter()


@router.post("/partidas", response_model=PartidaPublica, status_code=201)
def criar_partida(entrada: CriarPartida, db: Session = Depends(get_db)):
    return partidas.criar(db, entrada.jogador, entrada.categoria)


@router.post("/partidas/{partida_id}/respostas", response_model=ResultadoResposta)
def enviar_resposta(
    partida_id: str,
    entrada: EnviarResposta,
    db: Session = Depends(get_db),
):
    return partidas.responder(
        db, partida_id, entrada.pergunta_id, entrada.alternativa
    )
