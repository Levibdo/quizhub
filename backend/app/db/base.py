from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models after Base is defined so they are registered in its metadata.
from app.models import Categoria, Pergunta  # noqa: E402, F401
