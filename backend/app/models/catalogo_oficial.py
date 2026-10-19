from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.nem_a_pato import PerguntaNemPato
    from app.models.pergunta import Pergunta


class CatalogoOficial(Base):
    __tablename__ = "catalogos_oficiais"
    __table_args__ = (
        CheckConstraint(
            "modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')",
            name="ck_catalogos_oficiais_modo",
        ),
        CheckConstraint(
            "status IN ('PREPARADO', 'ATIVO', 'ARQUIVADO')",
            name="ck_catalogos_oficiais_status",
        ),
        CheckConstraint("versao >= 1", name="ck_catalogos_oficiais_versao_positiva"),
        UniqueConstraint(
            "catalogo_id", "versao", name="uq_catalogos_oficiais_id_versao"
        ),
        Index(
            "uq_catalogos_oficiais_modo_ativo",
            "modo",
            unique=True,
            postgresql_where=text("status = 'ATIVO'"),
            sqlite_where=text("status = 'ATIVO'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalogo_id: Mapped[str] = mapped_column(String(80), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    modo: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PREPARADO", server_default="PREPARADO"
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ativado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    perguntas_quiz: Mapped[list["Pergunta"]] = relationship(
        back_populates="catalogo_oficial"
    )
    perguntas_nem_pato: Mapped[list["PerguntaNemPato"]] = relationship(
        back_populates="catalogo_oficial"
    )


class FontePerguntaOficial(Base):
    __tablename__ = "fontes_perguntas_oficiais"
    __table_args__ = (
        UniqueConstraint(
            "pergunta_id", "ordem", name="uq_fontes_perguntas_oficiais_ordem"
        ),
        Index("ix_fontes_perguntas_oficiais_pergunta_id", "pergunta_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pergunta_id: Mapped[int] = mapped_column(
        ForeignKey("perguntas.id", ondelete="CASCADE"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    acessada_em: Mapped[date] = mapped_column(Date, nullable=False)

    pergunta: Mapped["Pergunta"] = relationship(back_populates="fontes_editoriais")


class FontePerguntaNemPatoOficial(Base):
    __tablename__ = "fontes_perguntas_nem_pato_oficiais"
    __table_args__ = (
        UniqueConstraint(
            "pergunta_id", "ordem",
            name="uq_fontes_perguntas_nem_pato_oficiais_ordem",
        ),
        Index("ix_fontes_perguntas_nem_pato_oficiais_pergunta_id", "pergunta_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pergunta_id: Mapped[int] = mapped_column(
        ForeignKey("perguntas_nem_pato.id", ondelete="CASCADE"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    acessada_em: Mapped[date] = mapped_column(Date, nullable=False)

    pergunta: Mapped["PerguntaNemPato"] = relationship(
        back_populates="fontes_editoriais"
    )
