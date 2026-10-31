from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON,
    String, Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.rascunho_catalogo_oficial import CatalogoOficialRascunho


class CicloRevisaoRascunho(Base):
    __tablename__ = "ciclos_revisao_rascunhos"
    __table_args__ = (
        CheckConstraint("estado IN ('EM_ANDAMENTO','CONCLUIDO','INVALIDADO')", name="ck_ciclos_revisao_estado"),
        CheckConstraint("revisao_conteudo >= 1 AND revisao_editorial >= 1", name="ck_ciclos_revisao_revisoes"),
        Index("ix_ciclos_revisao_rascunho_estado", "rascunho_id", "estado"),
        Index("uq_ciclos_revisao_ativo", "rascunho_id", unique=True,
              postgresql_where=text("estado = 'EM_ANDAMENTO'"),
              sqlite_where=text("estado = 'EM_ANDAMENTO'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais_rascunhos.id", ondelete="RESTRICT"), nullable=False)
    revisao_conteudo: Mapped[int] = mapped_column(Integer, nullable=False)
    revisao_editorial: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hash_validacao: Mapped[str] = mapped_column(String(64), nullable=False)
    versao_regras: Mapped[str] = mapped_column(String(40), nullable=False)
    total_erros: Mapped[int] = mapped_column(Integer, nullable=False)
    total_avisos: Mapped[int] = mapped_column(Integer, nullable=False)
    total_informacoes: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False, default="EM_ANDAMENTO")
    responsavel_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_invalidacao: Mapped[str | None] = mapped_column(Text)
    rascunho: Mapped["CatalogoOficialRascunho"] = relationship()
    itens: Mapped[list["ItemRevisaoPergunta"]] = relationship(back_populates="ciclo")
    achados: Mapped[list["AchadoValidacaoRascunhoPersistido"]] = relationship(back_populates="ciclo")


class AchadoValidacaoRascunhoPersistido(Base):
    __tablename__ = "achados_validacao_rascunhos"
    __table_args__ = (
        CheckConstraint("severidade IN ('ERRO','AVISO','INFORMACAO')", name="ck_achados_revisao_severidade"),
        UniqueConstraint("ciclo_id", "fingerprint", name="uq_achados_revisao_fingerprint"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ciclo_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ciclos_revisao_rascunhos.id", ondelete="RESTRICT"), nullable=False, index=True)
    codigo: Mapped[str] = mapped_column(String(80), nullable=False)
    severidade: Mapped[str] = mapped_column(String(16), nullable=False)
    pergunta_id: Mapped[UUID | None] = mapped_column(Uuid)
    id_editorial: Mapped[str | None] = mapped_column(String(80))
    campo: Mapped[str | None] = mapped_column(String(80))
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    recomendacao: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ciclo: Mapped[CicloRevisaoRascunho] = relationship(back_populates="achados")


class ItemRevisaoPergunta(Base):
    __tablename__ = "itens_revisao_perguntas"
    __table_args__ = (
        CheckConstraint("(pergunta_quiz_id IS NOT NULL) <> (pergunta_nem_pato_id IS NOT NULL)", name="ck_itens_revisao_uma_pergunta"),
        CheckConstraint("estado IN ('PENDENTE','APROVADA','CORRECAO_SOLICITADA','REPROVADA')", name="ck_itens_revisao_estado"),
        CheckConstraint("revisao_pergunta >= 1 AND revisao_editorial >= 1", name="ck_itens_revisao_revisoes"),
        UniqueConstraint("ciclo_id", "id_editorial", name="uq_itens_revisao_editorial"),
        Index("ix_itens_revisao_ciclo_estado", "ciclo_id", "estado"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ciclo_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ciclos_revisao_rascunhos.id", ondelete="RESTRICT"), nullable=False)
    pergunta_quiz_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("perguntas_quiz_rascunhos.id", ondelete="RESTRICT"))
    pergunta_nem_pato_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("perguntas_nem_pato_rascunhos.id", ondelete="RESTRICT"))
    id_editorial: Mapped[str] = mapped_column(String(80), nullable=False)
    revisao_pergunta: Mapped[int] = mapped_column(Integer, nullable=False)
    revisao_editorial: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDENTE")
    revisor_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ciclo: Mapped[CicloRevisaoRascunho] = relationship(back_populates="itens")
    decisoes: Mapped[list["DecisaoRevisaoPergunta"]] = relationship(back_populates="item")


class DecisaoRevisaoPergunta(Base):
    __tablename__ = "decisoes_revisao_perguntas"
    __table_args__ = (CheckConstraint("decisao IN ('APROVADA','CORRECAO_SOLICITADA','REPROVADA')", name="ck_decisoes_revisao_decisao"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("itens_revisao_perguntas.id", ondelete="RESTRICT"), nullable=False, index=True)
    decisao: Mapped[str] = mapped_column(String(24), nullable=False)
    justificativa: Mapped[str] = mapped_column(Text, nullable=False)
    relacao_fontes_resposta: Mapped[str | None] = mapped_column(Text)
    responsavel_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    revisao_anterior: Mapped[int] = mapped_column(Integer, nullable=False)
    revisao_nova: Mapped[int] = mapped_column(Integer, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    item: Mapped[ItemRevisaoPergunta] = relationship(back_populates="decisoes")


class VerificacaoFonteRevisao(Base):
    __tablename__ = "verificacoes_fontes_revisao"
    __table_args__ = (
        CheckConstraint("resultado IN ('CONSULTADA','SUFICIENTE','INSUFICIENTE','REJEITADA')", name="ck_verificacoes_fontes_resultado"),
        CheckConstraint("fonte_quiz_id IS NULL OR fonte_nem_pato_id IS NULL", name="ck_verificacoes_fontes_uma_fonte"),
        Index("ix_verificacoes_fontes_item_resultado", "item_id", "resultado"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("itens_revisao_perguntas.id", ondelete="RESTRICT"), nullable=False)
    fonte_quiz_id: Mapped[int | None] = mapped_column(ForeignKey("fontes_perguntas_quiz_rascunhos.id", ondelete="SET NULL"))
    fonte_nem_pato_id: Mapped[int | None] = mapped_column(ForeignKey("fontes_perguntas_nem_pato_rascunhos.id", ondelete="SET NULL"))
    fonte_titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    fonte_url: Mapped[str] = mapped_column(Text, nullable=False)
    fonte_acessada_em: Mapped[str] = mapped_column(String(10), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    resultado: Mapped[str] = mapped_column(String(16), nullable=False)
    evidencia_documental: Mapped[str] = mapped_column(Text, nullable=False)
    relacao_com_resposta: Mapped[str | None] = mapped_column(Text)
    justificativa: Mapped[str | None] = mapped_column(Text)
    responsavel_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DecisaoAvisoValidacao(Base):
    __tablename__ = "decisoes_avisos_validacao"
    __table_args__ = (
        CheckConstraint("decisao IN ('ACEITO','REJEITADO')", name="ck_decisoes_avisos_decisao"),
        UniqueConstraint("ciclo_id", "achado_id", name="uq_decisoes_avisos_achado"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ciclo_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ciclos_revisao_rascunhos.id", ondelete="RESTRICT"), nullable=False)
    achado_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("achados_validacao_rascunhos.id", ondelete="RESTRICT"), nullable=False)
    decisao: Mapped[str] = mapped_column(String(16), nullable=False)
    justificativa: Mapped[str] = mapped_column(Text, nullable=False)
    responsavel_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TransicaoRascunhoEditorial(Base):
    __tablename__ = "transicoes_rascunhos_editoriais"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais_rascunhos.id", ondelete="RESTRICT"), nullable=False, index=True)
    estado_anterior: Mapped[str] = mapped_column(String(24), nullable=False)
    estado_novo: Mapped[str] = mapped_column(String(24), nullable=False)
    revisao_conteudo: Mapped[int] = mapped_column(Integer, nullable=False)
    justificativa: Mapped[str] = mapped_column(Text, nullable=False)
    responsavel_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    operacao: Mapped[str] = mapped_column(String(80), nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AprovacaoRascunho(Base):
    __tablename__ = "aprovacoes_rascunhos"
    __table_args__ = (
        UniqueConstraint("ciclo_id", name="uq_aprovacoes_rascunhos_ciclo"),
        CheckConstraint("revisao_conteudo >= 1", name="ck_aprovacoes_revisao"),
        Index("ix_aprovacoes_rascunho_valida", "rascunho_id", "valida"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rascunho_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("catalogos_oficiais_rascunhos.id", ondelete="RESTRICT"), nullable=False)
    ciclo_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ciclos_revisao_rascunhos.id", ondelete="RESTRICT"), nullable=False)
    revisao_conteudo: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_validacao: Mapped[str] = mapped_column(String(64), nullable=False)
    responsavel_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    confirmacao_explicita: Mapped[bool] = mapped_column(Boolean, nullable=False)
    autorrevisao: Mapped[bool] = mapped_column(Boolean, nullable=False)
    justificativa_autorrevisao: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invalidada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_invalidacao: Mapped[str | None] = mapped_column(Text)
