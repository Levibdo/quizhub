from uuid import UUID

from pydantic import BaseModel, Field


class PartidaRankingPessoal(BaseModel):
    posicao: int = Field(ge=1)
    partida_id: UUID
    pontuacao: int = Field(ge=0)


class CategoriaRankingPessoal(BaseModel):
    categoria_id: UUID
    categoria_nome: str
    partidas: list[PartidaRankingPessoal]
