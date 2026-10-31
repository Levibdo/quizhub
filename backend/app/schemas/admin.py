from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CriarCatalogoInicial(BaseModel):
    catalogo_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    modo: str = Field(pattern=r"^(QUIZ_CLASSICO|NEM_A_PATO)$")


class CatalogoAdministrativo(BaseModel):
    id: UUID
    catalogo_id: str
    versao: int
    modo: str
    status: str
    sha256: str
    criado_em: datetime
    ativado_em: datetime | None
    arquivado_em: datetime | None

    model_config = {"from_attributes": True}


class CatalogoOficialConsulta(BaseModel):
    id: UUID
    catalogo_id: str
    modo: str
    versao: int
    status_registro: str
    estado_editorial: str | None
    situacao_ativacao: str
    quantidade_perguntas: int
    quantidade_elegivel_reativacao: int
    elegivel_reativacao: bool
    criado_em: datetime
    ativado_em: datetime | None
    arquivado_em: datetime | None


class ListaCatalogosOficiais(BaseModel):
    catalogos: list[CatalogoOficialConsulta]


class ReativarCatalogoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    justificativa: str = Field(min_length=10, max_length=2000)


class ReativacaoCatalogoPublica(BaseModel):
    catalogo_id: UUID
    identificador: str
    modo: str
    versao: int
    status: str
    versao_anterior_id: UUID
    versao_anterior: int
    perguntas_elegiveis: int


class ReferenciaEditorialAdministrativa(BaseModel):
    titulo: str
    url: str
    acessada_em: date


class CategoriaPerguntaAdministrativa(BaseModel):
    id: UUID
    slug: str
    nome: str


class CatalogoPerguntaAdministrativa(BaseModel):
    id: UUID
    catalogo_id: str
    versao: int
    status: str


class CatalogoPerguntaOpcao(CatalogoPerguntaAdministrativa):
    modo: str


class CategoriaPerguntaOpcao(CategoriaPerguntaAdministrativa):
    modo: str


class PerguntaOficialResumo(BaseModel):
    id: int
    id_editorial: str | None
    modo: str
    enunciado: str
    ativa: bool
    dificuldade: str | None
    categoria: CategoriaPerguntaAdministrativa
    catalogo: CatalogoPerguntaAdministrativa


class PaginaPerguntasOficiais(BaseModel):
    itens: list[PerguntaOficialResumo]
    pagina: int
    limite: int
    total: int
    total_paginas: int


class OpcoesPerguntasOficiais(BaseModel):
    catalogos: list[CatalogoPerguntaOpcao]
    categorias: list[CategoriaPerguntaOpcao]


class FonteLegadaNemPatoAdministrativa(BaseModel):
    nome: str | None
    url: str | None
    acessada_em: date | None


class PerguntaOficialDetalhe(PerguntaOficialResumo):
    explicacao: str
    alternativas: list[str] | None
    alternativa_correta: int | None
    resposta_numerica: str | None
    unidade: str | None
    tema_editorial: str | None
    natureza_resposta: str | None
    qualificacao_estimativa: str | None
    fonte_legada: FonteLegadaNemPatoAdministrativa | None
    referencias: list[ReferenciaEditorialAdministrativa]


class AuditoriaAdministrativaPublica(BaseModel):
    id: UUID
    administrador_id: UUID
    administrador_nome: str
    ocorrida_em: datetime
    operacao: str
    recurso_tipo: str
    recurso_id: str | None
    resultado: str
    catalogo_id: str | None
    catalogo_versao: int | None
    detalhes: dict | None


class PaginaAuditoriaAdministrativa(BaseModel):
    itens: list[AuditoriaAdministrativaPublica]
    pagina: int
    limite: int
    total: int
    total_paginas: int


class ResumoAdministrativo(BaseModel):
    catalogos: list[CatalogoAdministrativo]
    auditorias: list[AuditoriaAdministrativaPublica]


class ContagemAtivosAdministrativa(BaseModel):
    total: int
    ativos: int


class ContagemOrigemAdministrativa(BaseModel):
    total: int
    oficiais: int
    privadas: int


class ContagemPartidasModoAdministrativa(BaseModel):
    total: int
    concluidas: int


class ContagemPartidasAdministrativa(BaseModel):
    total: int
    concluidas: int
    quiz_classico: ContagemPartidasModoAdministrativa
    nem_a_pato: ContagemPartidasModoAdministrativa


class IndicadoresAdministrativos(BaseModel):
    usuarios: ContagemAtivosAdministrativa
    partidas: ContagemPartidasAdministrativa
    perguntas: ContagemOrigemAdministrativa
    categorias: ContagemOrigemAdministrativa
    catalogos_oficiais_ativos: int


class TemporadaAdministrativa(BaseModel):
    id: UUID
    numero: int
    nome: str
    status: str
    inicia_em: datetime
    encerra_em: datetime | None

    model_config = {"from_attributes": True}


class DashboardAdministrativo(ResumoAdministrativo):
    indicadores: IndicadoresAdministrativos
    temporada_ativa: TemporadaAdministrativa | None


class TokenCsrfAdministrativo(BaseModel):
    token: str
    expira_em_segundos: int
