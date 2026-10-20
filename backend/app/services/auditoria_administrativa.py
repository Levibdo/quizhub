from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditoriaAdministrativa, Usuario
from app.services.seguranca_administrativa import sanitizar_detalhes_auditoria


def registrar_auditoria_administrativa(
    db: Session,
    administrador: Usuario,
    *,
    operacao: str,
    recurso_tipo: str,
    resultado: str,
    recurso_id: str | UUID | None = None,
    catalogo_id: str | None = None,
    catalogo_versao: int | None = None,
    detalhes: dict | None = None,
) -> AuditoriaAdministrativa:
    """Registra metadados operacionais; o chamador controla a transação."""
    registro = AuditoriaAdministrativa(
        administrador_id=administrador.id,
        operacao=operacao,
        recurso_tipo=recurso_tipo,
        recurso_id=str(recurso_id) if recurso_id is not None else None,
        resultado=resultado,
        catalogo_id=catalogo_id,
        catalogo_versao=catalogo_versao,
        detalhes=sanitizar_detalhes_auditoria(detalhes),
    )
    db.add(registro)
    return registro
