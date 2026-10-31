from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

Modo = Literal["QUIZ_CLASSICO", "NEM_A_PATO"]
Dificuldade = Literal["FACIL", "MEDIA", "DIFICIL"]
Natureza = Literal["EXATA", "ESTIMATIVA"]


class FonteRascunho(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=4000)
    acessada_em: date


class FonteRascunhoPublica(FonteRascunho):
    id: int


class CriarRascunho(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1, max_length=160)


class DescartarRascunho(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=1, max_length=2000)


class PerguntaQuizRascunhoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_editorial: str = Field(min_length=1, max_length=80)
    categoria_id: UUID
    enunciado: str = Field(min_length=1)
    alternativas: list[str] = Field(min_length=4, max_length=4)
    alternativa_correta: int = Field(ge=0, le=3)
    explicacao: str = Field(min_length=1)
    dificuldade: Dificuldade
    ativa: bool = True
    referencias: list[FonteRascunho] = Field(min_length=1)

    @field_validator("alternativas")
    @classmethod
    def alternativas_validas(cls, valores):
        if any(not item.strip() for item in valores):
            raise ValueError("alternativas não podem ser vazias")
        return [item.strip() for item in valores]


class PerguntaNemPatoRascunhoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_editorial: str = Field(min_length=1, max_length=80)
    categoria_id: UUID
    enunciado: str = Field(min_length=1)
    resposta_numerica: str
    unidade: str | None = None
    explicacao: str = Field(min_length=1)
    fonte: str | None = None
    fonte_url: str | None = None
    fonte_acessada_em: date | None = None
    tema_editorial: str | None = Field(default=None, max_length=100)
    natureza_resposta: Natureza
    qualificacao_estimativa: str | None = None
    ativa: bool = True
    referencias: list[FonteRascunho] = Field(min_length=1)

    @field_validator("resposta_numerica")
    @classmethod
    def bigint_valido(cls, valor):
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            raise ValueError("resposta numérica deve ser um inteiro") from None
        if numero < 0 or numero > 2**63 - 1:
            raise ValueError("resposta numérica fora do intervalo BIGINT")
        return str(numero)


class RascunhoResumo(BaseModel):
    id: UUID
    catalogo_origem_id: UUID
    catalogo_id: str
    modo: Modo
    versao_base: int
    numero_rascunho: int
    nome: str
    status: str
    revisao: int
    criado_por_id: UUID
    modificado_por_id: UUID
    criado_em: datetime
    atualizado_em: datetime
    descartado_em: datetime | None
    motivo_descarte: str | None
    total_perguntas: int = 0
    adicionadas: int = 0
    modificadas: int = 0
    removidas: int = 0
    model_config = ConfigDict(from_attributes=True)


class PaginaRascunhos(BaseModel):
    itens: list[RascunhoResumo]
    pagina: int
    limite: int
    total: int
    total_paginas: int


class PerguntaRascunhoResumo(BaseModel):
    id: UUID
    id_editorial: str
    categoria_id: UUID
    categoria_slug: str
    categoria_nome: str
    ordem: int
    enunciado: str
    ativa: bool
    tipo_alteracao: str
    revisao: int
    dificuldade: str | None = None


class PaginaPerguntasRascunho(BaseModel):
    itens: list[PerguntaRascunhoResumo]
    pagina: int
    limite: int
    total: int
    total_paginas: int


class PerguntaRascunhoDetalhe(PerguntaRascunhoResumo):
    explicacao: str
    alternativas: list[str] | None = None
    alternativa_correta: int | None = None
    resposta_numerica: str | None = None
    unidade: str | None = None
    fonte: str | None = None
    fonte_url: str | None = None
    fonte_acessada_em: date | None = None
    tema_editorial: str | None = None
    natureza_resposta: str | None = None
    qualificacao_estimativa: str | None = None
    referencias: list[FonteRascunhoPublica]


class AlteracaoRascunhoPublica(BaseModel):
    id: UUID
    pergunta_quiz_rascunho_id: UUID | None
    pergunta_nem_pato_rascunho_id: UUID | None
    administrador_id: UUID
    tipo: str
    id_editorial: str | None
    revisao_anterior: int | None
    revisao_nova: int
    campos_alterados: dict | None
    ocorrida_em: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginaAlteracoesRascunho(BaseModel):
    itens: list[AlteracaoRascunhoPublica]
    pagina: int
    limite: int
    total: int
    total_paginas: int


class AchadoValidacaoRascunho(BaseModel):
    codigo: str
    nivel: Literal["ERRO", "AVISO", "INFORMACAO"]
    pergunta_id: UUID | None = None
    id_editorial: str | None = None
    campo: str | None = None
    mensagem: str
    recomendacao: str | None = None


class ResumoValidacaoRascunho(BaseModel):
    perguntas_examinadas: int
    perguntas_publicaveis: int
    perguntas_validas_estruturalmente: int
    perguntas_com_problemas: int
    erros: int
    avisos: int
    informacoes: int


class ValidacaoRascunhoOficial(BaseModel):
    rascunho_id: UUID
    catalogo_origem_id: UUID
    catalogo_id: str
    versao_base: int
    modo: Modo
    revisao_validada: int
    resumo: ResumoValidacaoRascunho
    achados: list[AchadoValidacaoRascunho]
