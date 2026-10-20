from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.schemas.perguntas import RelatorioImportacaoPerguntas
from app.security import exigir_csrf_admin
from app.services.auditoria_administrativa import registrar_auditoria_administrativa
from app.services.importador_perguntas import (
    ArquivoImportacaoInvalido,
    importador_perguntas,
)
from app.services.seguranca_administrativa import (
    ArquivoAdministrativoMuitoGrande,
    importacao_legada_habilitada,
    ler_upload_limitado,
    limite_importacao_legada,
)

router = APIRouter(prefix="/perguntas", tags=["perguntas"])
CABECALHOS_DEPRECIACAO = {
    "Deprecation": "true",
    "Warning": '299 - "Endpoint legado; use catalogos oficiais versionados"',
}


def _registrar_rejeicao(db, administrador, motivo: str, **detalhes) -> None:
    registrar_auditoria_administrativa(
        db, administrador,
        operacao="IMPORTAR_PERGUNTAS_LEGADO",
        recurso_tipo="PERGUNTAS_OFICIAIS",
        resultado="REJEITADA",
        detalhes={"motivo": motivo, **detalhes},
    )
    db.commit()


@router.post("/importar", response_model=RelatorioImportacaoPerguntas)
def importar_perguntas(
    response: Response,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    administrador: Usuario = Depends(exigir_csrf_admin),
):
    response.headers.update(CABECALHOS_DEPRECIACAO)
    if not importacao_legada_habilitada():
        _registrar_rejeicao(db, administrador, "IMPORTADOR_DESABILITADO")
        raise HTTPException(
            status_code=410,
            detail="importador legado desabilitado",
            headers=CABECALHOS_DEPRECIACAO,
        )
    if not arquivo.filename or not arquivo.filename.lower().endswith(".xlsx"):
        _registrar_rejeicao(db, administrador, "FORMATO_INVALIDO")
        raise HTTPException(
            status_code=422, detail="envie um arquivo XLSX",
            headers=CABECALHOS_DEPRECIACAO,
        )
    try:
        limite = limite_importacao_legada()
        conteudo = ler_upload_limitado(arquivo.file, limite)
        resultado = importador_perguntas.importar(
            db, conteudo, confirmar=False
        )
        registrar_auditoria_administrativa(
            db, administrador,
            operacao="IMPORTAR_PERGUNTAS_LEGADO",
            recurso_tipo="PERGUNTAS_OFICIAIS",
            resultado="SUCESSO",
            detalhes={"criadas": resultado.criadas, "falhas": resultado.falhas},
        )
        db.commit()
        return resultado
    except ArquivoAdministrativoMuitoGrande as erro:
        db.rollback()
        _registrar_rejeicao(
            db, administrador, "ARQUIVO_MUITO_GRANDE",
            limite_bytes=limite_importacao_legada(),
        )
        raise HTTPException(
            status_code=413, detail=str(erro), headers=CABECALHOS_DEPRECIACAO
        ) from erro
    except ArquivoImportacaoInvalido as erro:
        db.rollback()
        _registrar_rejeicao(db, administrador, "CONTEUDO_INVALIDO")
        raise HTTPException(
            status_code=422, detail=str(erro), headers=CABECALHOS_DEPRECIACAO
        ) from erro
    except Exception:
        db.rollback()
        try:
            registrar_auditoria_administrativa(
                db, administrador,
                operacao="IMPORTAR_PERGUNTAS_LEGADO",
                recurso_tipo="PERGUNTAS_OFICIAIS",
                resultado="FALHA",
                detalhes={"motivo": "FALHA_INTERNA"},
            )
            db.commit()
        except Exception:
            db.rollback()
        raise
