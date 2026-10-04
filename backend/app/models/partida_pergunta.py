from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.partida import Partida
    from app.models.pergunta import Pergunta
    from app.models.resposta import Resposta


class PartidaPergunta(Base):
    __tablename__ = "partida_perguntas"
    __table_args__ = (
        UniqueConstraint(
            "partida_id", "ordem", name="uq_partida_perguntas_partida_ordem"
        ),
        UniqueConstraint(
            "partida_id", "pergunta_id", name="uq_partida_perguntas_partida_pergunta"
        ),
        CheckConstraint("ordem >= 1", name="ck_partida_perguntas_ordem_positiva"),
        CheckConstraint(
            "prazo_resposta_em IS NULL OR disponibilizada_em IS NULL "
            "OR prazo_resposta_em > disponibilizada_em",
            name="ck_partida_perguntas_prazo_posterior",
        ),
        Index("ix_partida_perguntas_pergunta_id", "pergunta_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    partida_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partidas.id"), nullable=False
    )
    pergunta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("perguntas.id"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    disponibilizada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    prazo_resposta_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    categoria_id_snapshot: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    enunciado_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_a_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_b_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_c_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_d_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_correta_snapshot: Mapped[int] = mapped_column(
        SmallInteger, nullable=False
    )
    explicacao_snapshot: Mapped[str] = mapped_column(Text, nullable=False)

    partida: Mapped["Partida"] = relationship(back_populates="perguntas_partida")
    pergunta: Mapped["Pergunta"] = relationship(back_populates="partidas_pergunta")
    resposta: Mapped["Resposta | None"] = relationship(
        back_populates="partida_pergunta", uselist=False
    )
