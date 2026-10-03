from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CriarSalaNemAPato(BaseModel):
    nome: str = Field(min_length=1, max_length=100)

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("nome não pode ser vazio")
        return valor


class EntrarSalaNemAPato(CriarSalaNemAPato):
    pass


class ParticipanteSalaPublico(BaseModel):
    id: UUID
    nome: str
    ordem_entrada: int
    eh_anfitriao: bool
    status: str


class SalaLobbyPublica(BaseModel):
    codigo: str
    status: str
    versao: int
    criada_em: datetime
    participantes: list[ParticipanteSalaPublico]
    participantes_ativos: int
    limite_jogadores: int


class JogadorPartidaNemPatoPublico(BaseModel):
    nome: str
    ordem_circular: int
    status: str


class PartidaNemPatoPublica(BaseModel):
    id: UUID
    numero: int
    status: str
    rodada_atual: int
    total_rodadas: int
    duracao_rodada_segundos: int
    jogadores: list[JogadorPartidaNemPatoPublico]


class SalaRecuperada(BaseModel):
    sala: SalaLobbyPublica
    participante: ParticipanteSalaPublico
    partida: PartidaNemPatoPublica | None = None


class ParticipacaoSalaCriada(SalaRecuperada):
    credencial_participante: str