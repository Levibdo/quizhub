from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Pergunta(Base):
    __tablename__ = "perguntas"
    __table_args__ = (
        CheckConstraint(
            "alternativa_correta >= 0 AND alternativa_correta <= 3",
            name="ck_perguntas_alternativa_correta",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    categoria_id: Mapped[str] = mapped_column(
        String, ForeignKey("categorias.id"), nullable=False
    )
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_a: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_b: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_c: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_d: Mapped[str] = mapped_column(Text, nullable=False)
    alternativa_correta: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    categoria: Mapped["Categoria"] = relationship(back_populates="perguntas")


from app.models.categoria import Categoria  # noqa: E402
