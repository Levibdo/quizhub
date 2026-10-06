from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator,
)


AlternativaCorreta = Literal["A", "B", "C", "D"]


def _texto_obrigatorio(valor: str) -> str:
    normalizado = valor.strip()
    if not normalizado:
        raise ValueError("texto não pode ser vazio")
    return normalizado


def _texto_opcional(valor: str | None) -> str | None:
    if valor is None:
        return None
    return valor.strip() or None


class PerguntaClassicaCriar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID
    enunciado: str
    alternativa_a: str
    alternativa_b: str
    alternativa_c: str
    alternativa_d: str
    alternativa_correta: AlternativaCorreta
    explicacao: str

    @field_validator(
        "enunciado", "alternativa_a", "alternativa_b", "alternativa_c",
        "alternativa_d", "explicacao",
    )
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return _texto_obrigatorio(valor)


class PerguntaClassicaEditar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID | None = None
    enunciado: str | None = None
    alternativa_a: str | None = None
    alternativa_b: str | None = None
    alternativa_c: str | None = None
    alternativa_d: str | None = None
    alternativa_correta: AlternativaCorreta | None = None
    explicacao: str | None = None
    ativa: bool | None = None

    @field_validator(
        "categoria_id", "enunciado", "alternativa_a", "alternativa_b",
        "alternativa_c", "alternativa_d", "alternativa_correta", "explicacao",
        "ativa",
    )
    @classmethod
    def rejeitar_nulo(cls, valor):
        if valor is None:
            raise ValueError("campo não pode ser nulo")
        return valor

    @field_validator(
        "enunciado", "alternativa_a", "alternativa_b", "alternativa_c",
        "alternativa_d", "explicacao",
    )
    @classmethod
    def validar_texto(cls, valor: str | None) -> str | None:
        return _texto_obrigatorio(valor) if valor is not None else valor

    @model_validator(mode="after")
    def validar_payload(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("informe ao menos um campo")
        return self


class PerguntaClassicaResposta(BaseModel):
    id: int
    categoria_id: UUID
    enunciado: str
    alternativa_a: str
    alternativa_b: str
    alternativa_c: str
    alternativa_d: str
    alternativa_correta: AlternativaCorreta
    explicacao: str
    ativa: bool
    criada_em: datetime
    atualizada_em: datetime
    excluida_em: datetime | None


class PerguntaNemPatoCriar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID
    enunciado: str
    resposta_numerica: StrictInt = Field(ge=0, le=2**63 - 1)
    unidade: str | None = None
    explicacao: str
    fonte: str | None = None

    @field_validator("enunciado", "explicacao")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return _texto_obrigatorio(valor)

    @field_validator("unidade", "fonte")
    @classmethod
    def normalizar_opcional(cls, valor: str | None) -> str | None:
        return _texto_opcional(valor)


class PerguntaNemPatoEditar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID | None = None
    enunciado: str | None = None
    resposta_numerica: StrictInt | None = Field(
        default=None, ge=0, le=2**63 - 1
    )
    unidade: str | None = None
    explicacao: str | None = None
    fonte: str | None = None
    ativa: bool | None = None

    @field_validator(
        "categoria_id", "enunciado", "resposta_numerica", "explicacao", "ativa"
    )
    @classmethod
    def rejeitar_nulo(cls, valor):
        if valor is None:
            raise ValueError("campo não pode ser nulo")
        return valor

    @field_validator("enunciado", "explicacao")
    @classmethod
    def validar_texto(cls, valor: str | None) -> str | None:
        return _texto_obrigatorio(valor) if valor is not None else valor

    @field_validator("unidade", "fonte")
    @classmethod
    def normalizar_opcional(cls, valor: str | None) -> str | None:
        return _texto_opcional(valor)

    @model_validator(mode="after")
    def validar_payload(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("informe ao menos um campo")
        return self


class PerguntaNemPatoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria_id: UUID
    enunciado: str
    resposta_numerica: int
    unidade: str | None
    explicacao: str
    fonte: str | None
    ativa: bool
    criada_em: datetime
    atualizada_em: datetime
    excluida_em: datetime | None
