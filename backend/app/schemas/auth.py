from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class CadastroUsuario(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("nome não pode ser vazio")
        return valor

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, valor: EmailStr) -> str:
        return str(valor).strip().lower()


class LoginUsuario(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, valor: EmailStr) -> str:
        return str(valor).strip().lower()


class UsuarioPublico(BaseModel):
    id: UUID
    nome: str
    email: str
    ativo: bool
    criado_em: datetime

    model_config = {"from_attributes": True}
