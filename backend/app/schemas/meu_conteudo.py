from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.conteudo import MODO_NEM_A_PATO, MODO_QUIZ_CLASSICO


ModoConteudo = Literal["QUIZ_CLASSICO", "NEM_A_PATO"]


def _texto_opcional(valor: str | None) -> str | None:
    if valor is None:
        return None
    normalizado = valor.strip()
    return normalizado or None


class CategoriaUsuarioCriar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(max_length=100)
    descricao: str | None = None
    modo: ModoConteudo

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, valor: str) -> str:
        normalizado = valor.strip()
        if not normalizado:
            raise ValueError("nome não pode ser vazio")
        return normalizado

    @field_validator("descricao")
    @classmethod
    def normalizar_descricao(cls, valor: str | None) -> str | None:
        return _texto_opcional(valor)


class CategoriaUsuarioEditar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(default=None, max_length=100)
    descricao: str | None = None
    ativa: bool | None = None

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, valor: str | None) -> str | None:
        if valor is None:
            raise ValueError("nome não pode ser nulo")
        normalizado = valor.strip()
        if not normalizado:
            raise ValueError("nome não pode ser vazio")
        return normalizado

    @field_validator("descricao")
    @classmethod
    def normalizar_descricao(cls, valor: str | None) -> str | None:
        return _texto_opcional(valor)

    @field_validator("ativa")
    @classmethod
    def validar_ativa(cls, valor: bool | None) -> bool:
        if valor is None:
            raise ValueError("ativa não pode ser nula")
        return valor

    @model_validator(mode="after")
    def validar_payload(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("informe ao menos um campo")
        return self


class CategoriaUsuarioResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    nome: str
    descricao: str | None
    modo: ModoConteudo
    ativa: bool
    criada_em: datetime
    atualizada_em: datetime
    excluida_em: datetime | None


class UsoConteudo(BaseModel):
    usadas: int
    limite: int


class ResumoModoConteudo(BaseModel):
    modo: ModoConteudo
    categorias: UsoConteudo
    perguntas: UsoConteudo


class ResumoMeuConteudo(BaseModel):
    modos: list[ResumoModoConteudo]


MODOS_TIPADOS: tuple[ModoConteudo, ...] = (
    MODO_QUIZ_CLASSICO,
    MODO_NEM_A_PATO,
)
