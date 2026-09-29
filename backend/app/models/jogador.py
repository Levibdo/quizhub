from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.partida import Partida
    from app.models.usuario import Usuario


class Jogador(Base):
    __tablename__ = "jogadores"
    __table_args__ = (Index("ix_jogadores_usuario_id", "usuario_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    usuario_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=True
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    partidas: Mapped[list["Partida"]] = relationship(back_populates="jogador")
    usuario: Mapped["Usuario | None"] = relationship(back_populates="jogadores")
