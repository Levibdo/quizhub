from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.partida_pergunta import PartidaPergunta


class Resposta(Base):
    __tablename__ = "respostas"
    __table_args__ = (
        UniqueConstraint(
            "partida_pergunta_id", name="uq_respostas_partida_pergunta_id"
        ),
        CheckConstraint(
            "alternativa_selecionada IS NULL "
            "OR alternativa_selecionada BETWEEN 0 AND 3",
            name="ck_respostas_alternativa_valida",
        ),
        CheckConstraint(
            "pontos_ganhos >= 0", name="ck_respostas_pontos_nao_negativos"
        ),
        CheckConstraint(
            "(timeout = true "
            "AND alternativa_selecionada IS NULL "
            "AND correta IS NULL "
            "AND pontos_ganhos = 0) "
            "OR (timeout = false "
            "AND alternativa_selecionada IS NOT NULL "
            "AND correta IS NOT NULL)",
            name="ck_respostas_consistencia_timeout",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    partida_pergunta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partida_perguntas.id"), nullable=False
    )
    alternativa_selecionada: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    correta: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    timeout: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    pontos_ganhos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    respondida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    partida_pergunta: Mapped["PartidaPergunta"] = relationship(
        back_populates="resposta"
    )
