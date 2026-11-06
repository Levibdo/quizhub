from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String, Uuid,
    Text, UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.catalogo_oficial import CatalogoOficial, FontePerguntaOficial
    from app.models.partida_pergunta import PartidaPergunta


class Pergunta(Base):
    __tablename__ = "perguntas"
    __table_args__ = (
        CheckConstraint(
            "alternativa_correta >= 0 AND alternativa_correta <= 3",
            name="ck_perguntas_alternativa_correta",
        ),
        CheckConstraint(
            "origem IN ('OFICIAL', 'USUARIO')", name="ck_perguntas_origem"
        ),
        CheckConstraint(
            "(origem = 'OFICIAL' AND usuario_id IS NULL) OR "
            "(origem = 'USUARIO' AND usuario_id IS NOT NULL)",
            name="ck_perguntas_origem_usuario",
        ),
        CheckConstraint(
            "excluida_em IS NULL OR ativa IS FALSE",
            name="ck_perguntas_excluida_inativa",
        ),
        CheckConstraint(
            "origem <> 'OFICIAL' OR excluida_em IS NULL",
            name="ck_perguntas_oficial_nao_excluida",
        ),
        CheckConstraint(
            "dificuldade IN ('FACIL', 'MEDIA', 'DIFICIL') OR dificuldade IS NULL",
            name="ck_perguntas_dificuldade",
        ),
        UniqueConstraint(
            "catalogo_oficial_id", "id_editorial",
            name="uq_perguntas_catalogo_id_editorial",
        ),
        Index("ix_perguntas_catalogo_oficial_id", "catalogo_oficial_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    categoria_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("categorias.id"), nullable=False
    )
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_a: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_b: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_c: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_d: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_correta: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    explicacao: Mapped[str] = mapped_column(Text, nullable=False)
    dificuldade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    origem: Mapped[str] = mapped_column(
        String(16), nullable=False, default="OFICIAL", server_default="OFICIAL"
    )
    usuario_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=True
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    excluida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    catalogo_oficial_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalogos_oficiais.id", ondelete="RESTRICT"), nullable=True
    )
    categoria_versao_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("categorias_oficiais_versoes.id", ondelete="RESTRICT"), nullable=True
    )
    id_editorial: Mapped[str | None] = mapped_column(String(80), nullable=True)

    categoria: Mapped["Categoria"] = relationship(back_populates="perguntas")
    partidas_pergunta: Mapped[list["PartidaPergunta"]] = relationship(
        back_populates="pergunta"
    )
    catalogo_oficial: Mapped["CatalogoOficial | None"] = relationship(
        back_populates="perguntas_quiz"
    )
    categoria_versao = relationship("CategoriaOficialVersao")
    fontes_editoriais: Mapped[list["FontePerguntaOficial"]] = relationship(
        back_populates="pergunta", cascade="all, delete-orphan", order_by="FontePerguntaOficial.ordem"
    )


from app.models.categoria import Categoria  # noqa: E402
