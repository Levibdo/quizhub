from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint, Uuid, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CategoriaOficialVersao(Base):
    __tablename__ = "categorias_oficiais_versoes"
    __table_args__ = (
        CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_cat_of_versoes_modo"),
        CheckConstraint("length(trim(slug)) > 0 AND slug = lower(trim(slug))", name="ck_cat_of_versoes_slug"),
        CheckConstraint("length(trim(nome)) > 0 AND nome = trim(nome)", name="ck_cat_of_versoes_nome"),
        UniqueConstraint("catalogo_oficial_id", "categoria_id", name="uq_cat_of_versoes_catalogo_categoria"),
        UniqueConstraint("catalogo_oficial_id", "slug", name="uq_cat_of_versoes_catalogo_slug"),
        Index("ix_cat_of_versoes_identidade", "categoria_id", "catalogo_oficial_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    categoria_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("categorias.id", ondelete="RESTRICT"), nullable=False)
    catalogo_oficial_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais.id", ondelete="RESTRICT"), nullable=False)
    modo: Mapped[str] = mapped_column(String(20), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    origem_backfill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    categoria = relationship("Categoria")
    catalogo = relationship("CatalogoOficial")


class CategoriaOficialRascunho(Base):
    __tablename__ = "categorias_oficiais_rascunhos"
    __table_args__ = (
        CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_cat_of_rascunhos_modo"),
        CheckConstraint("tipo_alteracao IN ('INALTERADA', 'MODIFICADA', 'ADICIONADA', 'REMOVIDA')", name="ck_cat_of_rascunhos_alteracao"),
        CheckConstraint("revisao >= 1", name="ck_cat_of_rascunhos_revisao"),
        CheckConstraint("length(trim(slug)) > 0 AND slug = lower(trim(slug))", name="ck_cat_of_rascunhos_slug"),
        CheckConstraint("length(trim(nome)) > 0 AND nome = trim(nome)", name="ck_cat_of_rascunhos_nome"),
        UniqueConstraint("rascunho_id", "categoria_id", name="uq_cat_of_rascunhos_identidade"),
        UniqueConstraint("rascunho_id", "slug", name="uq_cat_of_rascunhos_slug"),
        Index("ix_cat_of_rascunhos_rascunho", "rascunho_id", "tipo_alteracao"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais_rascunhos.id", ondelete="CASCADE"), nullable=False)
    categoria_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("categorias.id", ondelete="RESTRICT"), nullable=False)
    categoria_versao_origem_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("categorias_oficiais_versoes.id", ondelete="RESTRICT"))
    modo: Mapped[str] = mapped_column(String(20), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tipo_alteracao: Mapped[str] = mapped_column(String(16), nullable=False, default="INALTERADA")
    revisao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    modificado_por_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rascunho = relationship("CatalogoOficialRascunho")
    categoria = relationship("Categoria")
    versao_origem = relationship("CategoriaOficialVersao")
    modificado_por = relationship("Usuario")
