from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
    from app.models.partida import Partida


class Temporada(Base):
    __tablename__ = "temporadas"
    __table_args__ = (
        CheckConstraint("numero > 0", name="ck_temporadas_numero_positivo"),
        CheckConstraint(
            "status IN ('PLANEJADA', 'ATIVA', 'ENCERRADA')",
            name="ck_temporadas_status",
        ),
        CheckConstraint(
            "encerra_em IS NULL OR encerra_em >= inicia_em",
            name="ck_temporadas_periodo_valido",
        ),
        CheckConstraint(
            "(status = 'ENCERRADA' AND encerra_em IS NOT NULL) OR "
            "(status IN ('PLANEJADA', 'ATIVA') AND encerra_em IS NULL)",
            name="ck_temporadas_encerramento_status",
        ),
        CheckConstraint(
            "length(trim(nome)) > 0 AND nome = trim(nome)",
            name="ck_temporadas_nome_normalizado",
        ),
        Index("uq_temporadas_numero", "numero", unique=True),
        Index(
            "uq_temporadas_ativa",
            "status",
            unique=True,
            postgresql_where=text("status = 'ATIVA'"),
            sqlite_where=text("status = 'ATIVA'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    inicia_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    encerra_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    partidas: Mapped[list["Partida"]] = relationship(back_populates="temporada")
