import random
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Categoria,
    Jogador,
    Partida,
    PartidaPergunta,
    Pergunta,
    Resposta,
    Usuario,
)
from app.schemas.partidas import PartidaPublica, PerguntaPublica, ResultadoResposta

QUANTIDADE_PERGUNTAS = 10
PRAZO_RESPOSTA_SEGUNDOS = 15


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PartidasPersistentes:
    @staticmethod
    def _chave_categoria(categoria: Categoria) -> str:
        if categoria.origem == "OFICIAL":
            return categoria.slug
        return f"privada:{categoria.id}"

    def __init__(self, relogio: Callable[[], datetime] = utc_now):
        self.relogio = relogio

    @staticmethod
    def _pergunta_publica(ocorrencia: PartidaPergunta) -> PerguntaPublica:
        return PerguntaPublica(
            id=ocorrencia.pergunta_id,
            pergunta=ocorrencia.enunciado_snapshot,
            alternativas=[
                ocorrencia.alternativa_a_snapshot,
                ocorrencia.alternativa_b_snapshot,
                ocorrencia.alternativa_c_snapshot,
                ocorrencia.alternativa_d_snapshot,
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
            categoria=self._chave_categoria(partida.categoria),
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
                self._pergunta_publica(pergunta_partida)
                if pergunta_partida is not None and partida.status == "EM_ANDAMENTO"
                else None
            ),
        )

    def criar(
        self,
        db: Session,
        jogador: str | None,
        categoria_id: str,
        usuario: Usuario | None = None,
    ) -> PartidaPublica:
        try:
            nome_jogador = usuario.nome if usuario is not None else jogador
            if nome_jogador is None:
                raise HTTPException(
                    status_code=422,
                    detail="jogador é obrigatório para partidas como convidado",
                )

            try:
                categoria_uuid = UUID(categoria_id)
            except (TypeError, ValueError, AttributeError):
                categoria_uuid = None

            autorizacao = Categoria.origem == "OFICIAL"
            if usuario is not None:
                autorizacao = or_(
                    autorizacao,
                    and_(
                        Categoria.origem == "USUARIO",
                        Categoria.usuario_id == usuario.id,
                    ),
                )
            identificador = (
                Categoria.id == categoria_uuid
                if categoria_uuid is not None
                else and_(
                    Categoria.slug == categoria_id,
                    Categoria.origem == "OFICIAL",
                )
            )
            categoria = db.scalar(
                select(Categoria).where(
                    identificador,
                    Categoria.modo == "QUIZ_CLASSICO",
                    Categoria.ativa.is_(True),
                    Categoria.excluida_em.is_(None),
                    autorizacao,
                )
            )
            if categoria is None:
                raise HTTPException(
                    status_code=422,
                    detail="categoria inexistente, inativa ou sem perguntas suficientes",
                )

            if categoria.origem == "OFICIAL":
                propriedade = and_(
                    Pergunta.origem == "OFICIAL",
                    Pergunta.usuario_id.is_(None),
                )
            else:
                propriedade = and_(
                    Pergunta.origem == "USUARIO",
                    Pergunta.usuario_id == usuario.id,
                )
            candidatas = list(
                db.scalars(
                    select(Pergunta).where(
                        Pergunta.categoria_id == categoria.id,
                        Pergunta.ativa.is_(True),
                        Pergunta.excluida_em.is_(None),
                        propriedade,
                    )
                )
            )
            if len(candidatas) < QUANTIDADE_PERGUNTAS:
                raise HTTPException(
                    status_code=422,
                    detail="categoria inexistente, inativa ou sem perguntas suficientes",
                )

            agora = self.relogio()
            jogador_db = Jogador(
                nome=nome_jogador,
                usuario=usuario,
            )
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
                    categoria_id_snapshot=pergunta.categoria_id,
                    enunciado_snapshot=pergunta.enunciado,
                    alternativa_a_snapshot=pergunta.alternativa_a,
                    alternativa_b_snapshot=pergunta.alternativa_b,
                    alternativa_c_snapshot=pergunta.alternativa_c,
                    alternativa_d_snapshot=pergunta.alternativa_d,
                    alternativa_correta_snapshot=pergunta.alternativa_correta,
                    explicacao_snapshot=pergunta.explicacao,
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
                correta = alternativa == atual.alternativa_correta_snapshot
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
            # A proxima pergunta so e revelada quando seu prazo comeca.
            exibida = None

            db.flush()
            resposta_publica = ResultadoResposta(
                **self._publica(partida, exibida).model_dump(),
                explicacao=atual.explicacao_snapshot,
                correta=correta,
                alternativa_correta=atual.alternativa_correta_snapshot,
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

    def avancar(self, db: Session, partida_id: str, pergunta_id: int) -> PartidaPublica:
        """Libera a proxima pergunta uma vez, sem renovar prazo em tentativas repetidas."""
        try:
            partida = db.scalar(self._consulta_partida_bloqueada(self._uuid_partida(partida_id)))
            if partida is None:
                raise HTTPException(status_code=404, detail="partida inexistente")
            if partida.status != "EM_ANDAMENTO":
                raise HTTPException(status_code=409, detail="partida encerrada")
            anterior = db.scalar(select(PartidaPergunta).where(
                PartidaPergunta.partida_id == partida.id,
                PartidaPergunta.pergunta_id == pergunta_id,
                PartidaPergunta.resposta.has(),
            ))
            if anterior is None:
                raise HTTPException(status_code=409, detail="pergunta ainda nao respondida")
            proxima = db.scalar(select(PartidaPergunta).where(
                PartidaPergunta.partida_id == partida.id,
                PartidaPergunta.ordem == anterior.ordem + 1,
                ~PartidaPergunta.resposta.has(),
            ).options(joinedload(PartidaPergunta.pergunta)))
            if proxima is None:
                raise HTTPException(status_code=409, detail="transicao ja concluida")
            if proxima.disponibilizada_em is None:
                proxima.disponibilizada_em = self.relogio()
                proxima.prazo_resposta_em = proxima.disponibilizada_em + timedelta(
                    seconds=PRAZO_RESPOSTA_SEGUNDOS
                )
            db.flush()
            publica = self._publica(partida, proxima)
            db.commit()
            return publica
        except Exception:
            db.rollback()
            raise


partidas = PartidasPersistentes()
