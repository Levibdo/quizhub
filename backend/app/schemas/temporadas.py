from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemporadaPublica(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero: int = Field(ge=1)
    nome: str
    status: str
    inicia_em: datetime
    encerra_em: datetime | None
