from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Integer, JSON, SmallInteger, String, Text, UniqueConstraint, Uuid, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.catalogo_oficial import CatalogoOficial
    from app.models.categoria import Categoria
    from app.models.usuario import Usuario


class CatalogoOficialRascunho(Base):
    __tablename__ = "catalogos_oficiais_rascunhos"
    __table_args__ = (
        CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_catalogos_rascunhos_modo"),
        CheckConstraint("status IN ('EM_EDICAO', 'EM_VALIDACAO', 'EM_REVISAO', 'APROVADO', 'DESCARTADO', 'PUBLICADO')", name="ck_catalogos_rascunhos_status"),
        CheckConstraint("versao_base >= 1", name="ck_catalogos_rascunhos_versao_base"),
        CheckConstraint("numero_rascunho >= 1", name="ck_catalogos_rascunhos_numero"),
        CheckConstraint("revisao >= 1", name="ck_catalogos_rascunhos_revisao"),
        CheckConstraint("(status = 'DESCARTADO' AND descartado_em IS NOT NULL) OR (status <> 'DESCARTADO' AND descartado_em IS NULL)", name="ck_catalogos_rascunhos_descarte"),
        CheckConstraint("(catalogo_publicado_id IS NULL AND publicado_em IS NULL) OR (status = 'PUBLICADO' AND catalogo_publicado_id IS NOT NULL AND publicado_em IS NOT NULL)", name="ck_catalogos_rascunhos_publicacao"),
        UniqueConstraint("catalogo_id", "numero_rascunho", name="uq_catalogos_rascunhos_numero"),
        Index("ix_catalogos_rascunhos_origem_status", "catalogo_origem_id", "status"),
        Index("ix_catalogos_rascunhos_status_atualizado", "status", "atualizado_em"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalogo_origem_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais.id", ondelete="RESTRICT"), nullable=False)
    catalogo_id: Mapped[str] = mapped_column(String(80), nullable=False)
    modo: Mapped[str] = mapped_column(String(20), nullable=False)
    versao_base: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_rascunho: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="EM_EDICAO", server_default="EM_EDICAO")
    revisao: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    criado_por_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    modificado_por_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    descartado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_descarte: Mapped[str | None] = mapped_column(Text)
    catalogo_publicado_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("catalogos_oficiais.id", ondelete="RESTRICT"), unique=True)
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    catalogo_origem: Mapped["CatalogoOficial"] = relationship(foreign_keys=[catalogo_origem_id])
    catalogo_publicado: Mapped["CatalogoOficial | None"] = relationship(foreign_keys=[catalogo_publicado_id])
    criado_por: Mapped["Usuario"] = relationship(foreign_keys=[criado_por_id])
    modificado_por: Mapped["Usuario"] = relationship(foreign_keys=[modificado_por_id])
    perguntas_quiz: Mapped[list["PerguntaQuizRascunho"]] = relationship(back_populates="rascunho", cascade="all, delete-orphan")
    perguntas_nem_pato: Mapped[list["PerguntaNemPatoRascunho"]] = relationship(back_populates="rascunho", cascade="all, delete-orphan")
    alteracoes: Mapped[list["AlteracaoRascunhoOficial"]] = relationship(back_populates="rascunho", cascade="all, delete-orphan")


class PerguntaQuizRascunho(Base):
    __tablename__ = "perguntas_quiz_rascunhos"
    __table_args__ = (
        CheckConstraint("alternativa_correta BETWEEN 0 AND 3", name="ck_perguntas_quiz_rascunhos_gabarito"),
        CheckConstraint("dificuldade IN ('FACIL', 'MEDIA', 'DIFICIL')", name="ck_perguntas_quiz_rascunhos_dificuldade"),
        CheckConstraint("tipo_alteracao IN ('INALTERADA', 'MODIFICADA', 'ADICIONADA', 'REMOVIDA')", name="ck_perguntas_quiz_rascunhos_alteracao"),
        CheckConstraint("revisao >= 1", name="ck_perguntas_quiz_rascunhos_revisao"),
        UniqueConstraint("rascunho_id", "id_editorial", name="uq_perguntas_quiz_rascunhos_editorial"),
        UniqueConstraint("rascunho_id", "ordem", name="uq_perguntas_quiz_rascunhos_ordem"),
        Index("ix_perguntas_quiz_rascunhos_categoria", "rascunho_id", "categoria_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais_rascunhos.id", ondelete="CASCADE"), nullable=False)
    pergunta_origem_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("perguntas.id", ondelete="RESTRICT"))
    id_editorial: Mapped[str] = mapped_column(String(80), nullable=False)
    categoria_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("categorias.id", ondelete="RESTRICT"), nullable=False)
    categoria_slug_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    categoria_nome_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_a: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_b: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_c: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_d: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_correta: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    explicacao: Mapped[str] = mapped_column(Text, nullable=False)
    dificuldade: Mapped[str] = mapped_column(String(8), nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tipo_alteracao: Mapped[str] = mapped_column(String(16), nullable=False, default="INALTERADA")
    revisao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    modificado_por_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rascunho: Mapped[CatalogoOficialRascunho] = relationship(back_populates="perguntas_quiz")
    categoria: Mapped["Categoria"] = relationship()
    fontes: Mapped[list["FontePerguntaQuizRascunho"]] = relationship(back_populates="pergunta", cascade="all, delete-orphan", order_by="FontePerguntaQuizRascunho.ordem")


class PerguntaNemPatoRascunho(Base):
    __tablename__ = "perguntas_nem_pato_rascunhos"
    __table_args__ = (
        CheckConstraint("resposta_numerica >= 0", name="ck_perguntas_np_rascunhos_resposta"),
        CheckConstraint("natureza_resposta IN ('EXATA', 'ESTIMATIVA')", name="ck_perguntas_np_rascunhos_natureza"),
        CheckConstraint("tipo_alteracao IN ('INALTERADA', 'MODIFICADA', 'ADICIONADA', 'REMOVIDA')", name="ck_perguntas_np_rascunhos_alteracao"),
        CheckConstraint("revisao >= 1", name="ck_perguntas_np_rascunhos_revisao"),
        UniqueConstraint("rascunho_id", "id_editorial", name="uq_perguntas_np_rascunhos_editorial"),
        UniqueConstraint("rascunho_id", "ordem", name="uq_perguntas_np_rascunhos_ordem"),
        Index("ix_perguntas_np_rascunhos_categoria", "rascunho_id", "categoria_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais_rascunhos.id", ondelete="CASCADE"), nullable=False)
    pergunta_origem_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("perguntas_nem_pato.id", ondelete="RESTRICT"))
    id_editorial: Mapped[str] = mapped_column(String(80), nullable=False)
    categoria_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("categorias.id", ondelete="RESTRICT"), nullable=False)
    categoria_slug_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    categoria_nome_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    resposta_numerica: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unidade: Mapped[str | None] = mapped_column(String)
    explicacao: Mapped[str] = mapped_column(Text, nullable=False)
    fonte: Mapped[str | None] = mapped_column(String)
    fonte_url: Mapped[str | None] = mapped_column(Text)
    fonte_acessada_em: Mapped[date | None] = mapped_column(Date)
    tema_editorial: Mapped[str | None] = mapped_column(String(100))
    natureza_resposta: Mapped[str] = mapped_column(String(16), nullable=False)
    qualificacao_estimativa: Mapped[str | None] = mapped_column(Text)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tipo_alteracao: Mapped[str] = mapped_column(String(16), nullable=False, default="INALTERADA")
    revisao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    modificado_por_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rascunho: Mapped[CatalogoOficialRascunho] = relationship(back_populates="perguntas_nem_pato")
    categoria: Mapped["Categoria"] = relationship()
    fontes: Mapped[list["FontePerguntaNemPatoRascunho"]] = relationship(back_populates="pergunta", cascade="all, delete-orphan", order_by="FontePerguntaNemPatoRascunho.ordem")


class FontePerguntaQuizRascunho(Base):
    __tablename__ = "fontes_perguntas_quiz_rascunhos"
    __table_args__ = (UniqueConstraint("pergunta_rascunho_id", "ordem", name="uq_fontes_quiz_rascunhos_ordem"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    pergunta_rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("perguntas_quiz_rascunhos.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    acessada_em: Mapped[date] = mapped_column(Date, nullable=False)
    pergunta: Mapped[PerguntaQuizRascunho] = relationship(back_populates="fontes")


class FontePerguntaNemPatoRascunho(Base):
    __tablename__ = "fontes_perguntas_nem_pato_rascunhos"
    __table_args__ = (UniqueConstraint("pergunta_rascunho_id", "ordem", name="uq_fontes_np_rascunhos_ordem"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    pergunta_rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("perguntas_nem_pato_rascunhos.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    acessada_em: Mapped[date] = mapped_column(Date, nullable=False)
    pergunta: Mapped[PerguntaNemPatoRascunho] = relationship(back_populates="fontes")


class AlteracaoRascunhoOficial(Base):
    __tablename__ = "alteracoes_rascunhos_oficiais"
    __table_args__ = (
        CheckConstraint("tipo IN ('CRIACAO', 'EDICAO', 'ADICAO', 'REMOCAO', 'RESTAURACAO', 'DESCARTE')", name="ck_alteracoes_rascunhos_tipo"),
        CheckConstraint("NOT (pergunta_quiz_rascunho_id IS NOT NULL AND pergunta_nem_pato_rascunho_id IS NOT NULL)", name="ck_alteracoes_rascunhos_uma_pergunta"),
        Index("ix_alteracoes_rascunhos_rascunho_data", "rascunho_id", "ocorrida_em"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais_rascunhos.id", ondelete="CASCADE"), nullable=False)
    pergunta_quiz_rascunho_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("perguntas_quiz_rascunhos.id", ondelete="CASCADE"))
    pergunta_nem_pato_rascunho_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("perguntas_nem_pato_rascunhos.id", ondelete="CASCADE"))
    categoria_rascunho_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("categorias_oficiais_rascunhos.id", ondelete="CASCADE"))
    administrador_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    id_editorial: Mapped[str | None] = mapped_column(String(80))
    revisao_anterior: Mapped[int | None] = mapped_column(Integer)
    revisao_nova: Mapped[int] = mapped_column(Integer, nullable=False)
    campos_alterados: Mapped[dict | None] = mapped_column(JSON)
    ocorrida_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rascunho: Mapped[CatalogoOficialRascunho] = relationship(back_populates="alteracoes")
    administrador: Mapped["Usuario"] = relationship()
