from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AlteracaoRascunhoOficial, Categoria, CategoriaOficialRascunho,
    CategoriaOficialVersao, CatalogoOficialRascunho,
    PerguntaNemPatoRascunho, PerguntaQuizRascunho, Usuario,
)
from app.services.auditoria_administrativa import registrar_auditoria_administrativa


def _erro(status: int, codigo: str, mensagem: str):
    raise HTTPException(status, {"codigo": codigo, "mensagem": mensagem})


def _rascunho(db: Session, rascunho_id: UUID, revisao: int | None = None):
    item = db.scalar(select(CatalogoOficialRascunho).where(
        CatalogoOficialRascunho.id == rascunho_id
    ).with_for_update())
    if item is None: _erro(404, "RASCUNHO_NAO_ENCONTRADO", "rascunho não encontrado")
    if item.status != "EM_EDICAO": _erro(409, "RASCUNHO_NAO_EDITAVEL", "o rascunho não está em edição")
    if revisao is not None and item.revisao != revisao: _erro(412, "REVISAO_DIVERGENTE", "o rascunho foi alterado")
    return item


def listar_categorias(db: Session, rascunho_id: UUID):
    return list(db.scalars(select(CategoriaOficialRascunho).where(
        CategoriaOficialRascunho.rascunho_id == rascunho_id
    ).order_by(CategoriaOficialRascunho.slug, CategoriaOficialRascunho.id)))


def salvar_categoria(db: Session, rascunho_id: UUID, categoria_id: UUID | None,
                     dados: dict, revisao: int, admin: Usuario):
    rascunho = _rascunho(db, rascunho_id, revisao)
    slug = dados["slug"].strip().lower()
    nome = dados["nome"].strip()
    conflito = db.scalar(select(CategoriaOficialRascunho.id).where(
        CategoriaOficialRascunho.rascunho_id == rascunho.id,
        CategoriaOficialRascunho.slug == slug,
        CategoriaOficialRascunho.categoria_id != categoria_id if categoria_id else True,
    ).limit(1))
    if conflito: _erro(409, "SLUG_CATEGORIA_DUPLICADO", "o slug já existe no rascunho")
    agora = datetime.now(timezone.utc)
    if categoria_id is None:
        identidade = Categoria(
            id=uuid4(), slug=slug, nome=nome, descricao=dados.get("descricao"),
            modo=rascunho.modo, origem="OFICIAL", ativa=False,
        )
        db.add(identidade); db.flush()
        item = CategoriaOficialRascunho(
            rascunho_id=rascunho.id, categoria_id=identidade.id, modo=rascunho.modo,
            slug=slug, nome=nome, descricao=dados.get("descricao"),
            ativa=dados.get("ativa", True), tipo_alteracao="ADICIONADA",
            modificado_por_id=admin.id,
        )
        db.add(item); db.flush(); tipo = "ADICAO"
    else:
        item = db.scalar(select(CategoriaOficialRascunho).where(
            CategoriaOficialRascunho.rascunho_id == rascunho.id,
            CategoriaOficialRascunho.categoria_id == categoria_id,
        ).with_for_update())
        if item is None: _erro(404, "CATEGORIA_RASCUNHO_NAO_ENCONTRADA", "categoria não encontrada")
        item.slug, item.nome, item.descricao = slug, nome, dados.get("descricao")
        item.ativa = dados.get("ativa", True)
        item.tipo_alteracao = "ADICIONADA" if item.tipo_alteracao == "ADICIONADA" else "MODIFICADA"
        item.revisao += 1; item.atualizada_em = agora; item.modificado_por_id = admin.id
        tipo = "EDICAO"
    anterior = rascunho.revisao
    rascunho.revisao += 1; rascunho.atualizado_em = agora; rascunho.modificado_por_id = admin.id
    db.add(AlteracaoRascunhoOficial(
        rascunho_id=rascunho.id, categoria_rascunho_id=item.id,
        administrador_id=admin.id, tipo=tipo, revisao_anterior=anterior,
        revisao_nova=rascunho.revisao,
        campos_alterados={"categoria_id": str(item.categoria_id), "slug": slug, "nome": nome},
    ))
    registrar_auditoria_administrativa(
        db, admin, operacao=f"{tipo}_CATEGORIA_OFICIAL_RASCUNHO",
        recurso_tipo="CATEGORIA_OFICIAL_RASCUNHO", recurso_id=item.id,
        resultado="SUCESSO", detalhes={"rascunho_id": str(rascunho.id)},
    )
    db.flush()
    return item, rascunho.revisao


def alterar_remocao_categoria(db: Session, rascunho_id: UUID, categoria_id: UUID,
                              revisao: int, admin: Usuario, *, restaurar: bool):
    rascunho = _rascunho(db, rascunho_id, revisao)
    item = db.scalar(select(CategoriaOficialRascunho).where(
        CategoriaOficialRascunho.rascunho_id == rascunho.id,
        CategoriaOficialRascunho.categoria_id == categoria_id,
    ).with_for_update())
    if item is None:
        _erro(404, "CATEGORIA_RASCUNHO_NAO_ENCONTRADA", "categoria não encontrada")
    if restaurar:
        if item.tipo_alteracao != "REMOVIDA":
            _erro(409, "CATEGORIA_NAO_REMOVIDA", "a categoria não está removida")
        origem = (db.get(CategoriaOficialVersao, item.categoria_versao_origem_id)
                  if item.categoria_versao_origem_id else None)
        if origem is None:
            item.tipo_alteracao = "ADICIONADA"
        elif (item.slug, item.nome, item.descricao, item.ativa) == (
            origem.slug, origem.nome, origem.descricao, origem.ativa,
        ):
            item.tipo_alteracao = "INALTERADA"
        else:
            item.tipo_alteracao = "MODIFICADA"
        tipo = "RESTAURACAO"
    else:
        if item.tipo_alteracao == "REMOVIDA":
            _erro(409, "CATEGORIA_JA_REMOVIDA", "a categoria já está removida")
        modelo = PerguntaQuizRascunho if rascunho.modo == "QUIZ_CLASSICO" else PerguntaNemPatoRascunho
        referencias = db.scalar(select(modelo.id).where(
            modelo.rascunho_id == rascunho.id,
            modelo.categoria_id == categoria_id,
            modelo.tipo_alteracao != "REMOVIDA",
        ).limit(1))
        if referencias:
            _erro(409, "CATEGORIA_EM_USO", "remova ou mova as perguntas desta categoria antes de removê-la")
        item.tipo_alteracao = "REMOVIDA"
        tipo = "REMOCAO"
    agora = datetime.now(timezone.utc)
    item.revisao += 1
    item.atualizada_em = agora
    item.modificado_por_id = admin.id
    anterior = rascunho.revisao
    rascunho.revisao += 1
    rascunho.atualizado_em = agora
    rascunho.modificado_por_id = admin.id
    db.add(AlteracaoRascunhoOficial(
        rascunho_id=rascunho.id, categoria_rascunho_id=item.id,
        administrador_id=admin.id, tipo=tipo, revisao_anterior=anterior,
        revisao_nova=rascunho.revisao,
        campos_alterados={"categoria_id": str(item.categoria_id), "tipo_alteracao": item.tipo_alteracao},
    ))
    registrar_auditoria_administrativa(
        db, admin, operacao=f"{tipo}_CATEGORIA_OFICIAL_RASCUNHO",
        recurso_tipo="CATEGORIA_OFICIAL_RASCUNHO", recurso_id=item.id,
        resultado="SUCESSO", detalhes={"rascunho_id": str(rascunho.id)},
    )
    db.flush()
    return item, rascunho.revisao
