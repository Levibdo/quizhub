from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.schemas.perguntas import RelatorioImportacaoPerguntas
from app.security import exigir_admin
from app.services.auditoria_administrativa import registrar_auditoria_administrativa
from app.services.importador_perguntas import (
    ArquivoImportacaoInvalido,
    importador_perguntas,
)

router = APIRouter(prefix="/perguntas", tags=["perguntas"])


@router.post("/importar", response_model=RelatorioImportacaoPerguntas)
def importar_perguntas(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    administrador: Usuario = Depends(exigir_admin),
):
    if not arquivo.filename or not arquivo.filename.lower().endswith(".xlsx"):
        registrar_auditoria_administrativa(
            db, administrador,
            operacao="IMPORTAR_PERGUNTAS_LEGADO",
            recurso_tipo="PERGUNTAS_OFICIAIS",
            resultado="REJEITADA",
            detalhes={"motivo": "FORMATO_INVALIDO"},
        )
        db.commit()
        raise HTTPException(status_code=422, detail="envie um arquivo XLSX")
    try:
        resultado = importador_perguntas.importar(db, arquivo.file.read())
        registrar_auditoria_administrativa(
            db, administrador,
            operacao="IMPORTAR_PERGUNTAS_LEGADO",
            recurso_tipo="PERGUNTAS_OFICIAIS",
            resultado="SUCESSO",
            detalhes={"criadas": resultado.criadas, "falhas": resultado.falhas},
        )
        db.commit()
        return resultado
    except ArquivoImportacaoInvalido as erro:
        db.rollback()
        registrar_auditoria_administrativa(
            db, administrador,
            operacao="IMPORTAR_PERGUNTAS_LEGADO",
            recurso_tipo="PERGUNTAS_OFICIAIS",
            resultado="REJEITADA",
            detalhes={"motivo": "CONTEUDO_INVALIDO"},
        )
        db.commit()
        raise HTTPException(status_code=422, detail=str(erro)) from erro
