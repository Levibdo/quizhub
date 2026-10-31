from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class MotivoEditorial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    justificativa: str = Field(min_length=10, max_length=4000)


class DecisaoPerguntaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisao: Literal["APROVADA", "CORRECAO_SOLICITADA", "REPROVADA"]
    justificativa: str = Field(min_length=10, max_length=4000)
    relacao_fontes_resposta: str | None = Field(default=None, max_length=4000)


class VerificacaoFonteEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resultado: Literal["CONSULTADA", "SUFICIENTE", "INSUFICIENTE", "REJEITADA"]
    evidencia_documental: str = Field(min_length=10, max_length=8000)
    relacao_com_resposta: str | None = Field(default=None, max_length=4000)
    justificativa: str | None = Field(default=None, max_length=4000)


class DecisaoAvisoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisao: Literal["ACEITO", "REJEITADO"]
    justificativa: str = Field(min_length=10, max_length=4000)


class SolicitarCorrecaoEntrada(MotivoEditorial):
    perguntas: list[UUID] = Field(min_length=1, max_length=500)


class AprovarRascunhoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmacao_explicita: bool
    justificativa_autorrevisao: str | None = Field(default=None, max_length=4000)


class RespostaOperacaoEditorial(BaseModel):
    rascunho_id: UUID
    ciclo_id: UUID | None = None
    status: str
    revisao_conteudo: int
    revisao_editorial: int | None = None
