from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import Temporada
from app.temporadas import (
    STATUS_TEMPORADA_ATIVA,
    STATUS_TEMPORADA_ENCERRADA,
    STATUS_TEMPORADA_PLANEJADA,
)


class TemporadaAtivaAusente(RuntimeError):
    pass


class TemporadaInexistente(LookupError):
    pass


class TemporadaInvalida(RuntimeError):
    pass


class TemporadasService:
    @staticmethod
    def ativa_para_nova_partida(db: Session) -> Temporada:
        """Lock shared with creations and exclusive with a future season switch."""
        consulta = (
            select(Temporada)
            .where(Temporada.status == STATUS_TEMPORADA_ATIVA)
            .with_for_update(read=True)
        )
        temporada = db.scalar(consulta)
        if temporada is None:
            # A row may stop matching while PostgreSQL waits for a concurrent
            # switch. A second statement gets a fresh READ COMMITTED snapshot.
            temporada = db.scalar(consulta)
        if temporada is None:
            raise TemporadaAtivaAusente("não existe temporada ativa")
        return temporada

    @staticmethod
    def ativa(db: Session) -> Temporada:
        temporada = db.scalar(
            select(Temporada).where(Temporada.status == STATUS_TEMPORADA_ATIVA)
        )
        if temporada is None:
            raise TemporadaAtivaAusente("não existe temporada ativa")
        return temporada

    @staticmethod
    def resolver(db: Session, identificador: str | UUID | int | None) -> Temporada:
        if identificador is None:
            return TemporadasService.ativa(db)
        if isinstance(identificador, int) or (
            isinstance(identificador, str) and identificador.isdecimal()
        ):
            numero = int(identificador)
            temporada = db.scalar(
                select(Temporada).where(Temporada.numero == numero)
            )
        else:
            try:
                temporada_id = (
                    identificador
                    if isinstance(identificador, UUID)
                    else UUID(str(identificador))
                )
            except (TypeError, ValueError, AttributeError) as erro:
                raise TemporadaInexistente("temporada inexistente") from erro
            temporada = db.get(Temporada, temporada_id)
        if temporada is None:
            raise TemporadaInexistente("temporada inexistente")
        if temporada.status == STATUS_TEMPORADA_PLANEJADA:
            raise TemporadaInexistente("temporada inexistente")
        return temporada

    @staticmethod
    def listar_publicas(db: Session) -> list[Temporada]:
        ativa_primeiro = case(
            (Temporada.status == STATUS_TEMPORADA_ATIVA, 0),
            else_=1,
        )
        return list(db.scalars(
            select(Temporada)
            .where(Temporada.status.in_((
                STATUS_TEMPORADA_ATIVA,
                STATUS_TEMPORADA_ENCERRADA,
            )))
            .order_by(ativa_primeiro, Temporada.numero.desc())
        ))

    @staticmethod
    def ativar(
        db: Session,
        temporada_id: UUID,
        *,
        temporada_atual_id: UUID,
        agora: datetime | None = None,
    ) -> Temporada:
        """Internal primitive for a future controlled switch; no route/command yet."""
        instante = agora or datetime.now(timezone.utc)
        atual = db.scalar(
            select(Temporada)
            .where(Temporada.status == STATUS_TEMPORADA_ATIVA)
            .with_for_update()
        )
        if atual is None:
            # Under PostgreSQL READ COMMITTED, a row that stops matching while
            # this SELECT waits for its lock may yield no result. Re-read in a
            # fresh statement to distinguish a concurrent switch from a real
            # absence of active season.
            atual_apos_espera = db.scalar(
                select(Temporada).where(
                    Temporada.status == STATUS_TEMPORADA_ATIVA
                )
            )
            if (
                atual_apos_espera is not None
                and atual_apos_espera.id != temporada_atual_id
            ):
                raise TemporadaInvalida(
                    "a temporada ativa mudou durante a ativação"
                )
            raise TemporadaAtivaAusente("não existe temporada ativa")
        if atual.id != temporada_atual_id:
            raise TemporadaInvalida("a temporada ativa mudou durante a ativação")
        destino = db.scalar(
            select(Temporada)
            .where(Temporada.id == temporada_id)
            .with_for_update()
        )
        if destino is None:
            raise TemporadaInexistente("temporada inexistente")
        if destino.status != STATUS_TEMPORADA_PLANEJADA:
            raise TemporadaInvalida("somente uma temporada planejada pode ser ativada")
        atual.status = STATUS_TEMPORADA_ENCERRADA
        atual.encerra_em = instante
        atual.atualizada_em = instante
        # Release the partial unique slot before marking the destination active.
        db.flush([atual])
        destino.status = STATUS_TEMPORADA_ATIVA
        destino.inicia_em = instante
        destino.encerra_em = None
        destino.atualizada_em = instante
        db.flush([destino])
        return destino


temporadas_service = TemporadasService()
