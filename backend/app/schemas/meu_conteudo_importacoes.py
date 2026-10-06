from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.meu_conteudo import ModoConteudo


class ArquivoImportacaoPreview(BaseModel):
    nome: str
    tamanho: int
    sha256: str


class QuotaImportacaoPreview(BaseModel):
    atual: int
    novas: int
    apos_confirmacao: int
    limite: int


class ReferenciaErroImportacao(BaseModel):
    tipo: Literal["linha", "item"]
    valor: int


class ErroImportacaoPrivada(BaseModel):
    escopo: Literal["registro"] = "registro"
    referencia: ReferenciaErroImportacao
    campo: str | None
    codigo: str
    mensagem: str


class PreviewImportacaoPrivada(BaseModel):
    modo: ModoConteudo
    formato: Literal["xlsx", "csv", "json"]
    arquivo: ArquivoImportacaoPreview
    quantidade_recebida: int
    quantidade_valida: int
    quantidade_invalida: int
    quota: QuotaImportacaoPreview
    pode_confirmar: bool
    erros: list[ErroImportacaoPrivada]
    preview: list[dict[str, Any]]
    token_preview: str | None
    expira_em: datetime | None


class ResultadoImportacaoPrivada(BaseModel):
    modo: ModoConteudo
    formato: Literal["xlsx", "csv", "json"]
    criadas: int
