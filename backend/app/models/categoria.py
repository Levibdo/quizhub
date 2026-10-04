from typing import TYPE_CHECKING

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text,
    UniqueConstraint, Uuid, func, text, true,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.nem_a_pato import PerguntaNemPato
    from app.models.partida import Partida
    from app.models.pergunta import Pergunta


class _NomeCategoriaNormalizado(FunctionElement):
    type = String()
    inherit_cache = True


@compiles(_NomeCategoriaNormalizado)
def _nome_categoria_normalizado(element, compiler, **kw):
    argumento = compiler.process(next(iter(element.clauses)), **kw)
    return f"lower(trim({argumento}))"


@compiles(_NomeCategoriaNormalizado, "postgresql")
def _nome_categoria_normalizado_postgresql(element, compiler, **kw):
    argumento = compiler.process(next(iter(element.clauses)), **kw)
    return f"lower(trim(BOTH FROM {argumento}))"


class Categoria(Base):
    __tablename__ = "categorias"
    __table_args__ = (
        CheckConstraint(
            "modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')",
            name="ck_categorias_modo",
        ),
        CheckConstraint(
            "origem IN ('OFICIAL', 'USUARIO')",
            name="ck_categorias_origem",
        ),
        CheckConstraint(
            "(origem = 'OFICIAL' AND usuario_id IS NULL) OR "
            "(origem = 'USUARIO' AND usuario_id IS NOT NULL)",
            name="ck_categorias_origem_usuario",
        ),
        CheckConstraint(
            "excluida_em IS NULL OR ativa IS FALSE",
            name="ck_categorias_excluida_inativa",
        ),
        CheckConstraint(
            "origem <> 'OFICIAL' OR excluida_em IS NULL",
            name="ck_categorias_oficial_nao_excluida",
        ),
        CheckConstraint(
            "length(trim(nome)) > 0 AND nome = trim(nome)",
            name="ck_categorias_nome_normalizado",
        ),
        CheckConstraint(
            "length(trim(slug)) > 0 AND slug = lower(trim(slug))",
            name="ck_categorias_slug_normalizado",
        ),
        UniqueConstraint("id", "modo", "origem", name="uq_categorias_id_modo_origem"),
        UniqueConstraint("id", "usuario_id", name="uq_categorias_id_usuario"),
        Index(
            "uq_categorias_oficial_modo_slug",
            "modo", "slug", unique=True,
            postgresql_where=text("origem = 'OFICIAL'"),
            sqlite_where=text("origem = 'OFICIAL'"),
        ),
        Index(
            "uq_categorias_usuario_modo_nome",
            "usuario_id", "modo",
            _NomeCategoriaNormalizado(text("nome")), unique=True,
            postgresql_where=text("origem = 'USUARIO' AND excluida_em IS NULL"),
            sqlite_where=text("origem = 'USUARIO' AND excluida_em IS NULL"),
        ),
        Index("ix_categorias_usuario_modo", "usuario_id", "modo"),
        Index("ix_categorias_catalogo", "modo", "origem", "ativa"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    modo: Mapped[str] = mapped_column(String(20), nullable=False)
    origem: Mapped[str] = mapped_column(String(16), nullable=False)
    usuario_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=True
    )
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    excluida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    perguntas: Mapped[list["Pergunta"]] = relationship(back_populates="categoria")
    partidas: Mapped[list["Partida"]] = relationship(back_populates="categoria")
    perguntas_nem_pato: Mapped[list["PerguntaNemPato"]] = relationship(
        back_populates="categoria"
    )
