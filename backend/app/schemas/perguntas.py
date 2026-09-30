from pydantic import BaseModel


class ErroImportacaoPergunta(BaseModel):
    linha: int
    motivo: str


class RelatorioImportacaoPerguntas(BaseModel):
    total: int
    criadas: int
    falhas: int
    erros: list[ErroImportacaoPergunta]


class RelatorioValidacaoPerguntas(BaseModel):
    formato: str
    total: int
    validas: int
    duplicadas: int
    invalidas: int
    erros: list[ErroImportacaoPergunta]
