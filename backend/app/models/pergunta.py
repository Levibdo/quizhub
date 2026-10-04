from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String, Uuid,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
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

    categoria: Mapped["Categoria"] = relationship(back_populates="perguntas")
    partidas_pergunta: Mapped[list["PartidaPergunta"]] = relationship(
        back_populates="pergunta"
    )


from app.models.categoria import Categoria  # noqa: E402
