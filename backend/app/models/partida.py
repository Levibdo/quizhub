from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.partida_pergunta import PartidaPergunta


class Partida(Base):
    __tablename__ = "partidas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('EM_ANDAMENTO', 'FINALIZADA', 'EXPIRADA')",
            name="ck_partidas_status",
        ),
        CheckConstraint("pontuacao >= 0", name="ck_partidas_pontuacao_nao_negativa"),
        CheckConstraint("acertos >= 0", name="ck_partidas_acertos_nao_negativos"),
        CheckConstraint("erros >= 0", name="ck_partidas_erros_nao_negativos"),
        Index("ix_partidas_jogador_id", "jogador_id"),
        Index("ix_partidas_categoria_id", "categoria_id"),
        Index("ix_partidas_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    jogador_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jogadores.id"), nullable=False
    )
    categoria_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("categorias.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="EM_ANDAMENTO",
        server_default=text("'EM_ANDAMENTO'"),
    )
    pontuacao: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    acertos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    erros: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    iniciada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finalizada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    jogador: Mapped["Jogador"] = relationship(back_populates="partidas")
    categoria: Mapped["Categoria"] = relationship(back_populates="partidas")
    perguntas_partida: Mapped[list["PartidaPergunta"]] = relationship(
        back_populates="partida"
    )


from app.models.categoria import Categoria  # noqa: E402
from app.models.jogador import Jogador  # noqa: E402
