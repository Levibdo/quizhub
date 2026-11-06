import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Usuario
from app.services.categorias_oficiais_rascunhos import listar_categorias, salvar_categoria
from app.services.rascunhos_catalogos_oficiais import adicionar_pergunta, criar_rascunho


def hash_conteudo(conteudo: dict) -> str:
    return hashlib.sha256(json.dumps(conteudo, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


def previsualizar(conteudo: dict) -> dict:
    modo = conteudo["modo"]
    perguntas = conteudo["perguntas_quiz"] if modo == "QUIZ_CLASSICO" else conteudo["perguntas_nem_pato"]
    indevidas = conteudo["perguntas_nem_pato"] if modo == "QUIZ_CLASSICO" else conteudo["perguntas_quiz"]
    if indevidas:
        raise HTTPException(422, {"codigo": "PERGUNTAS_MODO_INCOMPATIVEL", "mensagem": "o documento contém perguntas de outro modo"})
    slugs = {item["slug"] for item in conteudo["categorias"]}
    erros = [{"registro": indice, "campo": "categoria_slug", "codigo": "CATEGORIA_AUSENTE"}
             for indice, item in enumerate(perguntas) if item["categoria_slug"] not in slugs]
    return {"sha256": hash_conteudo(conteudo), "modo": modo,
            "total_categorias": len(slugs), "total_perguntas": len(perguntas),
            "valido": not erros, "erros": erros, "publicacao_automatica": False}


def confirmar(db: Session, catalogo_id: UUID, conteudo: dict, sha256_esperado: str,
              admin: Usuario):
    previa = previsualizar(conteudo)
    if previa["sha256"] != sha256_esperado:
        raise HTTPException(409, {"codigo": "CONTEUDO_IMPORTACAO_DIVERGENTE", "mensagem": "o conteúdo diverge da pré-visualização"})
    if not previa["valido"]:
        raise HTTPException(422, {"codigo": "IMPORTACAO_INVALIDA", "erros": previa["erros"]})
    rascunho = criar_rascunho(db, catalogo_id, conteudo["nome_rascunho"], admin)
    if rascunho.modo != conteudo["modo"]:
        raise HTTPException(409, {"codigo": "MODO_CATALOGO_DIVERGENTE", "mensagem": "o modo não corresponde ao catálogo"})
    revisao = rascunho.revisao
    existentes = {item.slug: item for item in listar_categorias(db, rascunho.id)}
    categorias = {}
    for dados in conteudo["categorias"]:
        atual = existentes.get(dados["slug"])
        item, revisao = salvar_categoria(db, rascunho.id,
            atual.categoria_id if atual else None, dados, revisao, admin)
        categorias[item.slug] = item.categoria_id
    perguntas = conteudo["perguntas_quiz"] if rascunho.modo == "QUIZ_CLASSICO" else conteudo["perguntas_nem_pato"]
    for dados in perguntas:
        entrada = dict(dados)
        entrada["categoria_id"] = categorias[entrada.pop("categoria_slug")]
        entrada["ativa"] = True
        if rascunho.modo == "QUIZ_CLASSICO":
            pass
        else:
            entrada.setdefault("fonte", None); entrada.setdefault("fonte_url", None); entrada.setdefault("fonte_acessada_em", None)
        _, revisao = adicionar_pergunta(db, rascunho.id, entrada, admin, revisao)
    return rascunho, revisao, previa
