from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CategoriaRankingPublica(BaseModel):
    id: UUID
    slug: str
    nome: str


class ItemRankingPublico(BaseModel):
    posicao: int = Field(ge=1)
    jogador: str
    categoria: CategoriaRankingPublica
    pontuacao: int = Field(ge=0)
    acertos: int = Field(ge=0)
    erros: int = Field(ge=0)
    finalizada_em: datetime | None
