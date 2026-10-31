from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import CatalogoOficial, Categoria, Pergunta, PerguntaNemPato, Usuario
from app.services.auditoria_administrativa import registrar_auditoria_administrativa

MINIMO_OPERACIONAL = 10


def _falhar(status: int, codigo: str, mensagem: str) -> None:
    raise HTTPException(status, {"codigo": codigo, "mensagem": mensagem})


def _antes_de_reativar(_db: Session, _alvo: CatalogoOficial) -> None:
    """Ponto interno de observabilidade e teste do rollback transacional."""


def _perguntas_elegiveis(db: Session, catalogo: CatalogoOficial) -> int:
    if catalogo.modo == "NEM_A_PATO":
        total = db.scalar(select(func.count(PerguntaNemPato.id)).join(Categoria).where(
            PerguntaNemPato.catalogo_oficial_id == catalogo.id,
            PerguntaNemPato.origem == "OFICIAL", PerguntaNemPato.usuario_id.is_(None),
            PerguntaNemPato.ativa.is_(True), PerguntaNemPato.excluida_em.is_(None),
            Categoria.modo == "NEM_A_PATO", Categoria.origem == "OFICIAL",
            Categoria.usuario_id.is_(None), Categoria.ativa.is_(True),
            Categoria.excluida_em.is_(None), PerguntaNemPato.fontes_editoriais.any(),
        )) or 0
        if total < MINIMO_OPERACIONAL:
            _falhar(422, "CATALOGO_SEM_MINIMO_OPERACIONAL", "a versão exige ao menos 10 perguntas Nem a Pato elegíveis e com fontes")
        return total
    if catalogo.modo != "QUIZ_CLASSICO":
        _falhar(409, "MODO_CATALOGO_INVALIDO", "o modo da versão é inválido")
    contagens = list(db.execute(select(Categoria.id, func.count(Pergunta.id)).join(
        Pergunta, Pergunta.categoria_id == Categoria.id
    ).where(
        Pergunta.catalogo_oficial_id == catalogo.id,
        Pergunta.origem == "OFICIAL", Pergunta.usuario_id.is_(None),
        Pergunta.ativa.is_(True), Pergunta.excluida_em.is_(None),
        Pergunta.fontes_editoriais.any(), Categoria.modo == "QUIZ_CLASSICO",
        Categoria.origem == "OFICIAL", Categoria.usuario_id.is_(None),
        Categoria.ativa.is_(True), Categoria.excluida_em.is_(None),
    ).group_by(Categoria.id)))
    total = sum(quantidade for _, quantidade in contagens)
    if not any(quantidade >= MINIMO_OPERACIONAL for _, quantidade in contagens):
        _falhar(422, "CATALOGO_SEM_MINIMO_OPERACIONAL", "a versão exige ao menos uma categoria oficial ativa com 10 perguntas elegíveis e com fontes")
    return total


def reativar_catalogo_oficial(db: Session, catalogo_id: UUID, ativo_esperado_id: UUID, admin: Usuario, justificativa: str) -> dict:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("LOCK TABLE catalogos_oficiais IN SHARE ROW EXCLUSIVE MODE"))
    alvo = db.scalar(select(CatalogoOficial).where(CatalogoOficial.id == catalogo_id).with_for_update())
    if alvo is None:
        _falhar(404, "CATALOGO_NAO_ENCONTRADO", "versão de catálogo não encontrada")
    if alvo.status != "ARQUIVADO":
        _falhar(409, "CATALOGO_NAO_ARQUIVADO", "somente uma versão arquivada pode ser reativada")
    ativo = db.scalar(select(CatalogoOficial).where(
        CatalogoOficial.modo == alvo.modo, CatalogoOficial.status == "ATIVO"
    ).with_for_update())
    if ativo is None:
        _falhar(409, "CATALOGO_ATIVO_AUSENTE", "não existe versão ativa para controlar a troca")
    if ativo.id != ativo_esperado_id:
        _falhar(412, "VERSAO_ATIVA_DIVERGENTE", "a versão ativa foi alterada; atualize os dados antes de tentar novamente")
    total = _perguntas_elegiveis(db, alvo)
    agora = datetime.now(timezone.utc)
    _antes_de_reativar(db, alvo)
    ativo.status, ativo.arquivado_em = "ARQUIVADO", agora
    db.flush()
    alvo.status, alvo.ativado_em, alvo.arquivado_em = "ATIVO", agora, None
    registrar_auditoria_administrativa(
        db, admin, operacao="REATIVAR_CATALOGO_OFICIAL", recurso_tipo="CATALOGO_OFICIAL",
        recurso_id=alvo.id, resultado="SUCESSO", catalogo_id=alvo.catalogo_id,
        catalogo_versao=alvo.versao, detalhes={
            "justificativa": justificativa, "modo": alvo.modo,
            "versao_anterior_id": str(ativo.id), "versao_anterior": ativo.versao,
            "perguntas_elegiveis": total,
        },
    )
    db.flush()
    return {"catalogo_id": str(alvo.id), "identificador": alvo.catalogo_id,
            "modo": alvo.modo, "versao": alvo.versao, "status": alvo.status,
            "versao_anterior_id": str(ativo.id), "versao_anterior": ativo.versao,
            "perguntas_elegiveis": total}
