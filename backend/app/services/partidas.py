import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException

from app.data.perguntas import PERGUNTAS, Pergunta
from app.schemas.partidas import PartidaPublica, PerguntaPublica, ResultadoResposta


@dataclass
class Partida:
    id: str
    jogador: str
    categoria: str
    perguntas: list[Pergunta]
    iniciada_em: datetime
    pergunta_disponibilizada_em: datetime
    pergunta_inicio_monotonico: float
    indice: int = 0
    pontuacao: int = 0
    acertos: int = 0
    erros: int = 0
    status: str = "EM_ANDAMENTO"
    finalizada_em: datetime | None = None


class PartidasEmMemoria:
    def __init__(self, relogio: Callable[[], float] = time.monotonic):
        self.relogio = relogio
        self.partidas: dict[str, Partida] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _publica(partida: Partida) -> PartidaPublica:
        pergunta = partida.perguntas[partida.indice] if partida.status == "EM_ANDAMENTO" else None
        return PartidaPublica(
            partida_id=partida.id,
            jogador=partida.jogador,
            categoria=partida.categoria,
            status=partida.status,
            iniciada_em=partida.iniciada_em,
            pergunta_disponibilizada_em=partida.pergunta_disponibilizada_em,
            finalizada_em=partida.finalizada_em,
            pontuacao=partida.pontuacao,
            acertos=partida.acertos,
            erros=partida.erros,
            pergunta_atual=PerguntaPublica(id=pergunta.id, pergunta=pergunta.pergunta, alternativas=list(pergunta.alternativas)) if pergunta else None,
        )

    def criar(self, jogador: str, categoria: str) -> PartidaPublica:
        candidatas = [pergunta for pergunta in PERGUNTAS if pergunta.categoria == categoria]
        if len(candidatas) < 3:
            raise HTTPException(status_code=422, detail="categoria inexistente ou sem perguntas suficientes")
        with self._lock:
            agora = datetime.now(timezone.utc)
            partida = Partida(
                id=str(uuid4()), jogador=jogador, categoria=categoria,
                perguntas=random.sample(candidatas, 3), iniciada_em=agora,
                pergunta_disponibilizada_em=agora,
                pergunta_inicio_monotonico=self.relogio(),
            )
            self.partidas[partida.id] = partida
            return self._publica(partida)

    def responder(self, partida_id: str, pergunta_id: int, alternativa: int) -> ResultadoResposta:
        with self._lock:
            partida = self.partidas.get(partida_id)
            if partida is None:
                raise HTTPException(status_code=404, detail="partida inexistente")
            if partida.status != "EM_ANDAMENTO":
                raise HTTPException(status_code=409, detail="partida já finalizada")
            pergunta = partida.perguntas[partida.indice]
            if pergunta_id != pergunta.id:
                raise HTTPException(status_code=409, detail="pergunta não é a atual ou já foi respondida")
            if alternativa < 0 or alternativa >= len(pergunta.alternativas):
                raise HTTPException(status_code=422, detail="alternativa fora do intervalo")

            decorrido = max(0.0, self.relogio() - partida.pergunta_inicio_monotonico)
            timeout = decorrido >= 15
            correta = None if timeout else alternativa == pergunta.correta
            segundos_restantes = max(0, min(15, ceil(15 - decorrido)))
            pontos_ganhos = 100 + segundos_restantes * 10 if correta else 0
            partida.pontuacao += pontos_ganhos
            if correta:
                partida.acertos += 1
            else:
                partida.erros += 1

            partida.indice += 1
            if partida.indice == len(partida.perguntas):
                partida.status = "FINALIZADA"
                partida.finalizada_em = datetime.now(timezone.utc)
            else:
                partida.pergunta_disponibilizada_em = datetime.now(timezone.utc)
                partida.pergunta_inicio_monotonico = self.relogio()

            return ResultadoResposta(
                **self._publica(partida).model_dump(),
                correta=correta, timeout=timeout, pontos_ganhos=pontos_ganhos,
            )


partidas = PartidasEmMemoria()
