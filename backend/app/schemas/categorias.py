from pydantic import BaseModel


class CategoriaPublica(BaseModel):
    id: str
    nome: str
    descricao: str | None
