from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models after Base is defined so they are registered in its metadata.
from app.models import (  # noqa: E402, F401
    Categoria,
    Jogador,
    JogadorPartidaNemPato,
    PalpiteNemPato,
    Partida,
    PartidaNemPato,
    ParticipanteNemPato,
    PartidaPergunta,
    Pergunta,
    PerguntaNemPato,
    Resposta,
    RodadaNemPato,
    SalaNemPato,
    Usuario,
)
