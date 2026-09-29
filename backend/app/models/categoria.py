from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.pergunta import Pergunta


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    perguntas: Mapped[list["Pergunta"]] = relationship(back_populates="categoria")
