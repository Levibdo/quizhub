from datetime import datetime
from typing import Annotated
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
    id: UUID
    nome: str
    ordem_circular: int
    status: str
    eh_eu: bool = False
    patos: int


class PerguntaRodadaNemPatoPublica(BaseModel):
    id: int
    categoria_id: str
    enunciado: str
    unidade: str | None


class PerguntaResultadoNemPatoPublica(PerguntaRodadaNemPatoPublica):
    resposta_numerica: int
    explicacao: str


class PalpiteNemPatoPublico(BaseModel):
    ordem: int
    valor: int
    jogador: JogadorPartidaNemPatoPublico
    criado_em: datetime


class ResultadoDesafioNemPatoPublico(BaseModel):
    desafiante: JogadorPartidaNemPatoPublico
    palpite_desafiado: PalpiteNemPatoPublico
    jogador_penalizado: JogadorPartidaNemPatoPublico
    resolvido_em: datetime


class RodadaNemPatoPublica(BaseModel):
    id: int
    numero: int
    status: str
    pergunta: PerguntaResultadoNemPatoPublica | PerguntaRodadaNemPatoPublica | None
    jogador_inicial: JogadorPartidaNemPatoPublico
    jogador_da_vez: JogadorPartidaNemPatoPublico | None
    maior_palpite: int | None
    palpites: list[PalpiteNemPatoPublico]
    iniciada_em: datetime | None
    termina_em: datetime | None
    finalizada_em: datetime | None = None
    tipo_finalizacao: str | None = None
    resultado_desafio: ResultadoDesafioNemPatoPublico | None = None


class PartidaNemPatoPublica(BaseModel):
    id: UUID
    numero: int
    status: str
    rodada_atual: int
    total_rodadas: int
    duracao_rodada_segundos: int
    jogadores: list[JogadorPartidaNemPatoPublico]
    rodada: RodadaNemPatoPublica | None = None


class CriarPalpiteNemPato(BaseModel):
    valor: Annotated[int, Field(strict=True, ge=0, le=9_223_372_036_854_775_807)]
    client_action_id: UUID


class CriarDesafioNemPato(BaseModel):
    client_action_id: UUID


class SalaRecuperada(BaseModel):
    sala: SalaLobbyPublica
    participante: ParticipanteSalaPublico
    partida: PartidaNemPatoPublica | None = None


class ParticipacaoSalaCriada(SalaRecuperada):
    credencial_participante: str
