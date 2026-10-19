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
