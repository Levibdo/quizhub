from fastapi import APIRouter

from app.schemas.partidas import CriarPartida, EnviarResposta, PartidaPublica, ResultadoResposta
from app.services.partidas import partidas

router = APIRouter()


@router.post("/partidas", response_model=PartidaPublica, status_code=201)
def criar_partida(entrada: CriarPartida):
    return partidas.criar(entrada.jogador, entrada.categoria)


@router.post("/partidas/{partida_id}/respostas", response_model=ResultadoResposta)
def enviar_resposta(partida_id: str, entrada: EnviarResposta):
    return partidas.responder(partida_id, entrada.pergunta_id, entrada.alternativa)
