import random
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import Categoria, Jogador, Partida, PartidaPergunta, Pergunta, Resposta
from app.schemas.partidas import PartidaPublica, PerguntaPublica, ResultadoResposta

QUANTIDADE_PERGUNTAS = 3
PRAZO_RESPOSTA_SEGUNDOS = 15


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PartidasPersistentes:
    def __init__(self, relogio: Callable[[], datetime] = utc_now):
        self.relogio = relogio

    @staticmethod
    def _pergunta_publica(pergunta: Pergunta) -> PerguntaPublica:
        return PerguntaPublica(
            id=pergunta.id,
            pergunta=pergunta.enunciado,
            alternativas=[
                pergunta.alternativa_a,
                pergunta.alternativa_b,
                pergunta.alternativa_c,
                pergunta.alternativa_d,
            ],
        )

    def _publica(
        self,
        partida: Partida,
        pergunta_partida: PartidaPergunta | None,
    ) -> PartidaPublica:
        return PartidaPublica(
            partida_id=str(partida.id),
            jogador=partida.jogador.nome,
            categoria=partida.categoria_id,
            status=partida.status,
            iniciada_em=partida.iniciada_em,
            pergunta_disponibilizada_em=(
                pergunta_partida.disponibilizada_em if pergunta_partida else None
            ),
            finalizada_em=partida.finalizada_em,
            pontuacao=partida.pontuacao,
            acertos=partida.acertos,
            erros=partida.erros,
            pergunta_atual=(
                self._pergunta_publica(pergunta_partida.pergunta)
                if pergunta_partida is not None and partida.status == "EM_ANDAMENTO"
                else None
            ),
        )

    def criar(self, db: Session, jogador: str, categoria_id: str) -> PartidaPublica:
        try:
            categoria = db.get(Categoria, categoria_id)
            if categoria is None or not categoria.ativa:
                raise HTTPException(
                    status_code=422,
                    detail="categoria inexistente, inativa ou sem perguntas suficientes",
                )

            candidatas = list(
                db.scalars(
                    select(Pergunta).where(
                        Pergunta.categoria_id == categoria_id,
                        Pergunta.ativa.is_(True),
                    )
                )
            )
            if len(candidatas) < QUANTIDADE_PERGUNTAS:
                raise HTTPException(
                    status_code=422,
                    detail="categoria inexistente, inativa ou sem perguntas suficientes",
                )

            agora = self.relogio()
            jogador_db = Jogador(nome=jogador)
            partida = Partida(
                jogador=jogador_db,
                categoria=categoria,
                status="EM_ANDAMENTO",
                iniciada_em=agora,
            )
            db.add(partida)

            perguntas_sorteadas = random.sample(candidatas, QUANTIDADE_PERGUNTAS)
            ocorrencias = []
            for ordem, pergunta in enumerate(perguntas_sorteadas, start=1):
                ocorrencia = PartidaPergunta(
                    partida=partida,
                    pergunta=pergunta,
                    ordem=ordem,
                    disponibilizada_em=agora if ordem == 1 else None,
                    prazo_resposta_em=(
                        agora + timedelta(seconds=PRAZO_RESPOSTA_SEGUNDOS)
                        if ordem == 1
                        else None
                    ),
                )
                ocorrencias.append(ocorrencia)
                db.add(ocorrencia)

            db.flush()
            resposta = self._publica(partida, ocorrencias[0])
            db.commit()
            return resposta
        except HTTPException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _uuid_partida(partida_id: str) -> UUID:
        try:
            return UUID(partida_id)
        except (TypeError, ValueError, AttributeError):
            raise HTTPException(status_code=404, detail="partida inexistente") from None

    @staticmethod
    def _consulta_partida_bloqueada(partida_id: UUID):
        return select(Partida).where(Partida.id == partida_id).with_for_update()

    def responder(
        self,
        db: Session,
        partida_id: str,
        pergunta_id: int,
        alternativa: int,
    ) -> ResultadoResposta:
        try:
            partida = db.scalar(
                self._consulta_partida_bloqueada(self._uuid_partida(partida_id))
            )
            if partida is None:
                raise HTTPException(status_code=404, detail="partida inexistente")
            if partida.status != "EM_ANDAMENTO":
                raise HTTPException(
                    status_code=409, detail="partida já finalizada ou expirada"
                )

            pendentes = list(
                db.scalars(
                    select(PartidaPergunta)
                    .where(
                        PartidaPergunta.partida_id == partida.id,
                        PartidaPergunta.disponibilizada_em.is_not(None),
                        ~PartidaPergunta.resposta.has(),
                    )
                    .options(joinedload(PartidaPergunta.pergunta))
                    .order_by(PartidaPergunta.ordem)
                )
            )
            if len(pendentes) != 1:
                raise HTTPException(
                    status_code=409, detail="estado persistido da partida inconsistente"
                )

            atual = pendentes[0]
            if atual.pergunta_id != pergunta_id:
                raise HTTPException(
                    status_code=409,
                    detail="pergunta não é a atual ou já foi respondida",
                )
            if atual.prazo_resposta_em is None:
                raise HTTPException(
                    status_code=409, detail="estado persistido da partida inconsistente"
                )

            agora = self.relogio()
            prazo = atual.prazo_resposta_em
            if prazo.tzinfo is None:
                prazo = prazo.replace(tzinfo=timezone.utc)
            timeout = agora >= prazo

            if timeout:
                correta = None
                alternativa_persistida = None
                pontos_ganhos = 0
            else:
                if alternativa < 0 or alternativa > 3:
                    raise HTTPException(
                        status_code=422, detail="alternativa fora do intervalo"
                    )
                correta = alternativa == atual.pergunta.alternativa_correta
                alternativa_persistida = alternativa
                segundos_restantes = max(
                    0,
                    min(
                        PRAZO_RESPOSTA_SEGUNDOS,
                        ceil((prazo - agora).total_seconds()),
                    ),
                )
                pontos_ganhos = (
                    100 + segundos_restantes * 10 if correta else 0
                )

            db.add(
                Resposta(
                    partida_pergunta=atual,
                    alternativa_selecionada=alternativa_persistida,
                    correta=correta,
                    timeout=timeout,
                    pontos_ganhos=pontos_ganhos,
                    respondida_em=agora,
                )
            )
            partida.pontuacao += pontos_ganhos
            if correta:
                partida.acertos += 1
            else:
                partida.erros += 1

            proxima = db.scalar(
                select(PartidaPergunta)
                .where(
                    PartidaPergunta.partida_id == partida.id,
                    PartidaPergunta.ordem == atual.ordem + 1,
                )
                .options(joinedload(PartidaPergunta.pergunta))
            )
            if proxima is None:
                partida.status = "FINALIZADA"
                partida.finalizada_em = agora
                exibida = atual
            else:
                proxima.disponibilizada_em = agora
                proxima.prazo_resposta_em = agora + timedelta(
                    seconds=PRAZO_RESPOSTA_SEGUNDOS
                )
                exibida = proxima

            db.flush()
            resposta_publica = ResultadoResposta(
                **self._publica(partida, exibida).model_dump(),
                correta=correta,
                timeout=timeout,
                pontos_ganhos=pontos_ganhos,
            )
            db.commit()
            return resposta_publica
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="pergunta já respondida"
            ) from error
        except Exception:
            db.rollback()
            raise


partidas = PartidasPersistentes()
