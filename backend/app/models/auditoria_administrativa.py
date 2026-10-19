from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.usuario import Usuario


class AuditoriaAdministrativa(Base):
    __tablename__ = "auditorias_administrativas"
    __table_args__ = (
        Index("ix_auditorias_administrativas_ocorrida_em", "ocorrida_em"),
        Index("ix_auditorias_administrativas_administrador_id", "administrador_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    administrador_id: Mapped[UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    ocorrida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    operacao: Mapped[str] = mapped_column(String(80), nullable=False)
    recurso_tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    recurso_id: Mapped[str | None] = mapped_column(String(160))
    resultado: Mapped[str] = mapped_column(String(24), nullable=False)
    catalogo_id: Mapped[str | None] = mapped_column(String(80))
    catalogo_versao: Mapped[int | None] = mapped_column(Integer)
    detalhes: Mapped[dict | None] = mapped_column(JSON)

    administrador: Mapped["Usuario"] = relationship()
