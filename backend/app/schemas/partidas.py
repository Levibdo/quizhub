from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class CriarPartida(BaseModel):
    jogador: str | None = None
    categoria: str

    @field_validator("jogador")
    @classmethod
    def validar_jogador(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            raise ValueError("jogador não pode ser vazio")
        return valor


class EnviarResposta(BaseModel):
    pergunta_id: int
    alternativa: int = Field(ge=0)


class PerguntaPublica(BaseModel):
    id: int
    pergunta: str
    alternativas: list[str]


class AvancarPergunta(BaseModel):
    pergunta_id: int


class PartidaPublica(BaseModel):
    partida_id: str
    jogador: str
    categoria: str
    status: str
    iniciada_em: datetime
    pergunta_disponibilizada_em: datetime | None
    prazo_resposta_em: datetime | None
    finalizada_em: datetime | None
    pontuacao: int
    acertos: int
    erros: int
    pergunta_atual: PerguntaPublica | None


class ResultadoResposta(PartidaPublica):
    explicacao: str
    correta: bool | None
    alternativa_correta: int
    timeout: bool
    pontos_ganhos: int


class FeedbackRespostaRecuperado(BaseModel):
    pergunta_id: int
    alternativa_selecionada: int | None
    explicacao: str
    correta: bool | None
    alternativa_correta: int
    timeout: bool
    pontos_ganhos: int


class PartidaRecuperada(PartidaPublica):
    fase: Literal[
        "AGUARDANDO_RESPOSTA",
        "AGUARDANDO_AVANCO",
        "FINALIZADA",
        "EXPIRADA",
    ]
    ordem_atual: int | None
    total_perguntas: int
    resultado_ultima_resposta: FeedbackRespostaRecuperado | None = None
