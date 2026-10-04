from pydantic import BaseModel
from uuid import UUID


class CategoriaPublica(BaseModel):
    id: UUID
    slug: str
    nome: str
    descricao: str | None
    modo: str
