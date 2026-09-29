from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.perguntas import RelatorioImportacaoPerguntas
from app.services.importador_perguntas import importador_perguntas

router = APIRouter(prefix="/perguntas", tags=["perguntas"])


@router.post("/importar", response_model=RelatorioImportacaoPerguntas)
def importar_perguntas(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not arquivo.filename or not arquivo.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="envie um arquivo XLSX")
    return importador_perguntas.importar(db, arquivo.file.read())
