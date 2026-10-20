from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
