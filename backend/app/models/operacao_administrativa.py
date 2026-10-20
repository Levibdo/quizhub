from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.usuario import Usuario


class OperacaoAdministrativa(Base):
    __tablename__ = "operacoes_administrativas"
    __table_args__ = (
        UniqueConstraint(
            "administrador_id",
            "tipo_operacao",
            "chave_idempotencia",
            name="uq_operacoes_admin_escopo_chave",
        ),
        CheckConstraint(
            "estado IN ('EM_ANDAMENTO', 'CONCLUIDA', 'FALHOU', 'INTERROMPIDA')",
            name="ck_operacoes_admin_estado",
        ),
        CheckConstraint("tentativas >= 1", name="ck_operacoes_admin_tentativas"),
        Index("ix_operacoes_admin_estado_atualizada", "estado", "atualizada_em"),
        Index("ix_operacoes_admin_administrador", "administrador_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    administrador_id: Mapped[UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    tipo_operacao: Mapped[str] = mapped_column(String(80), nullable=False)
    recurso_tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    recurso_id: Mapped[str | None] = mapped_column(String(160))
    chave_idempotencia: Mapped[str] = mapped_column(String(200), nullable=False)
    hash_requisicao: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(24), nullable=False, default="EM_ANDAMENTO",
        server_default="EM_ANDAMENTO",
    )
    codigo_resultado: Mapped[int | None] = mapped_column(Integer)
    resposta_sanitizada: Mapped[dict | None] = mapped_column(JSON)
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    administrador: Mapped["Usuario"] = relationship()
