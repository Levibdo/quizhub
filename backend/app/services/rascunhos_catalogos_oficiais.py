from datetime import datetime, timezone
from math import ceil
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    AlteracaoRascunhoOficial, CatalogoOficial, CatalogoOficialRascunho,
    Categoria, FontePerguntaNemPatoRascunho, FontePerguntaQuizRascunho,
    Pergunta, PerguntaNemPato, PerguntaNemPatoRascunho, PerguntaQuizRascunho,
    Usuario,
)
from app.services.auditoria_administrativa import registrar_auditoria_administrativa
from app.services.seguranca_administrativa import sanitizar_detalhes_auditoria


def _erro(codigo: int, chave: str, mensagem: str):
    return HTTPException(codigo, detail={"codigo": chave, "mensagem": mensagem})


def exigir_revisao(revisao: int | None) -> int:
    if revisao is None:
        raise _erro(status.HTTP_428_PRECONDITION_REQUIRED, "REVISAO_OBRIGATORIA", "a revisão esperada é obrigatória")
    if revisao < 1:
        raise _erro(422, "REVISAO_INVALIDA", "a revisão deve ser positiva")
    return revisao


def _rascunho_editavel(db: Session, rascunho_id: UUID, revisao: int, *, bloquear=True):
    consulta = select(CatalogoOficialRascunho).where(CatalogoOficialRascunho.id == rascunho_id)
    if bloquear:
        consulta = consulta.with_for_update()
    item = db.scalar(consulta)
    if item is None:
        raise _erro(404, "RASCUNHO_NAO_ENCONTRADO", "rascunho não encontrado")
    if item.status != "EM_EDICAO":
        raise _erro(409, "RASCUNHO_NAO_EDITAVEL", "o rascunho não está em edição")
    if item.revisao != revisao:
        raise _erro(412, "REVISAO_DIVERGENTE", "o rascunho foi alterado por outra operação")
    return item


def _categoria(db, categoria_id, modo):
    item = db.scalar(select(Categoria).where(
        Categoria.id == categoria_id, Categoria.origem == "OFICIAL",
        Categoria.modo == modo, Categoria.excluida_em.is_(None),
    ))
    if item is None:
        raise _erro(422, "CATEGORIA_OFICIAL_INVALIDA", "categoria oficial incompatível")
    return item


def _registrar_alteracao(db, rascunho, admin, tipo, anterior, nova, *, pergunta=None, campos=None):
    db.add(AlteracaoRascunhoOficial(
        rascunho_id=rascunho.id,
        pergunta_quiz_rascunho_id=(pergunta.id if isinstance(pergunta, PerguntaQuizRascunho) else None),
        pergunta_nem_pato_rascunho_id=(pergunta.id if isinstance(pergunta, PerguntaNemPatoRascunho) else None),
        administrador_id=admin.id, tipo=tipo,
        id_editorial=pergunta.id_editorial if pergunta else None,
        revisao_anterior=anterior, revisao_nova=nova,
        campos_alterados=sanitizar_detalhes_auditoria(campos),
    ))


def _avancar(rascunho, admin):
    anterior = rascunho.revisao
    rascunho.revisao += 1
    rascunho.modificado_por_id = admin.id
    rascunho.atualizado_em = datetime.now(timezone.utc)
    return anterior, rascunho.revisao


def criar_rascunho(db: Session, catalogo_id: UUID, nome: str, admin: Usuario):
    # Serializa a numeração de rascunhos derivados do mesmo catálogo.
    consulta = select(CatalogoOficial).where(CatalogoOficial.id == catalogo_id).with_for_update()
    origem = db.scalar(consulta)
    if origem is None:
        raise _erro(404, "CATALOGO_NAO_ENCONTRADO", "catálogo oficial não encontrado")
    numero = (db.scalar(select(func.max(CatalogoOficialRascunho.numero_rascunho)).where(
        CatalogoOficialRascunho.catalogo_id == origem.catalogo_id
    )) or 0) + 1
    rascunho = CatalogoOficialRascunho(
        catalogo_origem_id=origem.id, catalogo_id=origem.catalogo_id,
        modo=origem.modo, versao_base=origem.versao,
        numero_rascunho=numero, nome=nome.strip(),
        criado_por_id=admin.id, modificado_por_id=admin.id,
    )
    db.add(rascunho)
    db.flush()
    if origem.modo == "QUIZ_CLASSICO":
        perguntas = list(db.scalars(select(Pergunta).options(
            joinedload(Pergunta.categoria), selectinload(Pergunta.fontes_editoriais)
        ).where(Pergunta.catalogo_oficial_id == origem.id).order_by(Pergunta.id)))
        for ordem, item in enumerate(perguntas, 1):
            copia = PerguntaQuizRascunho(
                rascunho_id=rascunho.id, pergunta_origem_id=item.id,
                id_editorial=item.id_editorial, categoria_id=item.categoria_id,
                categoria_slug_snapshot=item.categoria.slug,
                categoria_nome_snapshot=item.categoria.nome, ordem=ordem,
                enunciado=item.enunciado, alternativa_a=item.alternativa_a,
                alternativa_b=item.alternativa_b, alternativa_c=item.alternativa_c,
                alternativa_d=item.alternativa_d,
                alternativa_correta=item.alternativa_correta,
                explicacao=item.explicacao, dificuldade=item.dificuldade,
                ativa=item.ativa, modificado_por_id=admin.id,
            )
            copia.fontes = [FontePerguntaQuizRascunho(
                ordem=f.ordem, titulo=f.titulo, url=f.url, acessada_em=f.acessada_em
            ) for f in item.fontes_editoriais]
            db.add(copia)
    else:
        perguntas = list(db.scalars(select(PerguntaNemPato).options(
            joinedload(PerguntaNemPato.categoria), selectinload(PerguntaNemPato.fontes_editoriais)
        ).where(PerguntaNemPato.catalogo_oficial_id == origem.id).order_by(PerguntaNemPato.id)))
        for ordem, item in enumerate(perguntas, 1):
            copia = PerguntaNemPatoRascunho(
                rascunho_id=rascunho.id, pergunta_origem_id=item.id,
                id_editorial=item.id_editorial, categoria_id=item.categoria_id,
                categoria_slug_snapshot=item.categoria.slug,
                categoria_nome_snapshot=item.categoria.nome, ordem=ordem,
                enunciado=item.enunciado, resposta_numerica=item.resposta_numerica,
                unidade=item.unidade, explicacao=item.explicacao, fonte=item.fonte,
                fonte_url=item.fonte_url, fonte_acessada_em=item.fonte_acessada_em,
                tema_editorial=item.tema_editorial,
                natureza_resposta=item.natureza_resposta or "EXATA",
                qualificacao_estimativa=item.qualificacao_estimativa,
                ativa=item.ativa, modificado_por_id=admin.id,
            )
            copia.fontes = [FontePerguntaNemPatoRascunho(
                ordem=f.ordem, titulo=f.titulo, url=f.url, acessada_em=f.acessada_em
            ) for f in item.fontes_editoriais]
            db.add(copia)
    _registrar_alteracao(db, rascunho, admin, "CRIACAO", None, 1, campos={"catalogo_origem_id": str(origem.id), "perguntas": len(perguntas)})
    registrar_auditoria_administrativa(db, admin, operacao="CRIAR_RASCUNHO_CATALOGO", recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho.id, catalogo_id=origem.catalogo_id, catalogo_versao=origem.versao, resultado="SUCESSO", detalhes={"numero_rascunho": numero, "perguntas": len(perguntas)})
    db.flush()
    return rascunho


def listar_rascunhos(db, *, pagina, limite, modo=None, status_rascunho=None):
    filtros = []
    if modo: filtros.append(CatalogoOficialRascunho.modo == modo)
    if status_rascunho: filtros.append(CatalogoOficialRascunho.status == status_rascunho)
    total = db.scalar(select(func.count()).select_from(CatalogoOficialRascunho).where(*filtros)) or 0
    itens = list(db.scalars(select(CatalogoOficialRascunho).where(*filtros).order_by(
        CatalogoOficialRascunho.atualizado_em.desc(), CatalogoOficialRascunho.id
    ).offset((pagina-1)*limite).limit(limite)))
    return itens, total, ceil(total/limite) if total else 0


def obter_rascunho(db, rascunho_id):
    return db.get(CatalogoOficialRascunho, rascunho_id)


def _modelo(rascunho):
    return PerguntaQuizRascunho if rascunho.modo == "QUIZ_CLASSICO" else PerguntaNemPatoRascunho


def listar_perguntas(db, rascunho, *, pagina, limite, busca=None, tipo_alteracao=None):
    modelo = _modelo(rascunho)
    filtros = [modelo.rascunho_id == rascunho.id]
    if busca: filtros.append(func.lower(modelo.enunciado).contains(busca.casefold(), autoescape=True))
    if tipo_alteracao: filtros.append(modelo.tipo_alteracao == tipo_alteracao)
    total = db.scalar(select(func.count()).select_from(modelo).where(*filtros)) or 0
    itens = list(db.scalars(select(modelo).where(*filtros).order_by(modelo.ordem, modelo.id).offset((pagina-1)*limite).limit(limite)))
    return itens, total, ceil(total/limite) if total else 0


def obter_pergunta(db, rascunho, pergunta_id):
    modelo = _modelo(rascunho)
    return db.scalar(select(modelo).options(selectinload(modelo.fontes)).where(modelo.id == pergunta_id, modelo.rascunho_id == rascunho.id))


def _dados_pergunta(item):
    campos = {"categoria_id": str(item.categoria_id), "enunciado": item.enunciado, "explicacao": item.explicacao, "ativa": item.ativa}
    if isinstance(item, PerguntaQuizRascunho):
        campos.update(alternativas=[item.alternativa_a, item.alternativa_b, item.alternativa_c, item.alternativa_d], alternativa_correta=item.alternativa_correta, dificuldade=item.dificuldade)
    else:
        campos.update(resposta_numerica=str(item.resposta_numerica), unidade=item.unidade, fonte=item.fonte, fonte_url=item.fonte_url, fonte_acessada_em=str(item.fonte_acessada_em) if item.fonte_acessada_em else None, tema_editorial=item.tema_editorial, natureza_resposta=item.natureza_resposta, qualificacao_estimativa=item.qualificacao_estimativa)
    campos["referencias"] = [{"titulo": f.titulo, "url": f.url, "acessada_em": str(f.acessada_em)} for f in item.fontes]
    return campos


def salvar_pergunta(db, rascunho_id, pergunta_id, payload, admin, revisao_esperada):
    rascunho = _rascunho_editavel(db, rascunho_id, exigir_revisao(revisao_esperada))
    item = obter_pergunta(db, rascunho, pergunta_id)
    if item is None: raise _erro(404, "PERGUNTA_RASCUNHO_NAO_ENCONTRADA", "pergunta do rascunho não encontrada")
    if payload["id_editorial"] != item.id_editorial:
        raise _erro(409, "ID_EDITORIAL_IMUTAVEL", "o ID editorial de uma pergunta existente não pode ser alterado")
    antes = _dados_pergunta(item)
    categoria = _categoria(db, payload["categoria_id"], rascunho.modo)
    item.categoria_id, item.categoria_slug_snapshot, item.categoria_nome_snapshot = categoria.id, categoria.slug, categoria.nome
    item.enunciado, item.explicacao, item.ativa = payload["enunciado"].strip(), payload["explicacao"].strip(), payload["ativa"]
    if rascunho.modo == "QUIZ_CLASSICO":
        item.alternativa_a, item.alternativa_b, item.alternativa_c, item.alternativa_d = payload["alternativas"]
        item.alternativa_correta, item.dificuldade = payload["alternativa_correta"], payload["dificuldade"]
        fonte_cls = FontePerguntaQuizRascunho
    else:
        for campo in ("unidade", "fonte", "fonte_url", "fonte_acessada_em", "tema_editorial", "natureza_resposta", "qualificacao_estimativa"):
            setattr(item, campo, payload.get(campo))
        item.resposta_numerica = int(payload["resposta_numerica"])
        fonte_cls = FontePerguntaNemPatoRascunho
    # Remove primeiro para não colidir com a unicidade (pergunta, ordem)
    # durante a substituição integral das referências.
    item.fontes.clear()
    db.flush()
    item.fontes = [fonte_cls(ordem=i, **fonte) for i, fonte in enumerate(payload["referencias"], 1)]
    item.tipo_alteracao = "ADICIONADA" if item.pergunta_origem_id is None else "MODIFICADA"
    item.revisao += 1; item.modificado_por_id = admin.id; item.atualizado_em = datetime.now(timezone.utc)
    anterior, nova = _avancar(rascunho, admin)
    depois = _dados_pergunta(item)
    diff = {k: {"antes": antes.get(k), "depois": v} for k, v in depois.items() if antes.get(k) != v}
    _registrar_alteracao(db, rascunho, admin, "EDICAO", anterior, nova, pergunta=item, campos=diff)
    registrar_auditoria_administrativa(db, admin, operacao="EDITAR_PERGUNTA_RASCUNHO", recurso_tipo="PERGUNTA_OFICIAL_RASCUNHO", recurso_id=item.id, catalogo_id=rascunho.catalogo_id, catalogo_versao=rascunho.versao_base, resultado="SUCESSO", detalhes={"campos": sorted(diff), "revisao": nova})
    db.flush(); return item, nova


def adicionar_pergunta(db, rascunho_id, payload, admin, revisao_esperada):
    rascunho = _rascunho_editavel(db, rascunho_id, exigir_revisao(revisao_esperada))
    categoria = _categoria(db, payload["categoria_id"], rascunho.modo)
    modelo = _modelo(rascunho)
    if db.scalar(select(modelo.id).where(modelo.rascunho_id == rascunho.id, modelo.id_editorial == payload["id_editorial"])):
        raise _erro(409, "ID_EDITORIAL_DUPLICADO", "ID editorial já existe no rascunho")
    ordem = (db.scalar(select(func.max(modelo.ordem)).where(modelo.rascunho_id == rascunho.id)) or 0) + 1
    comum = dict(rascunho_id=rascunho.id, id_editorial=payload["id_editorial"], categoria_id=categoria.id, categoria_slug_snapshot=categoria.slug, categoria_nome_snapshot=categoria.nome, ordem=ordem, enunciado=payload["enunciado"].strip(), explicacao=payload["explicacao"].strip(), ativa=payload["ativa"], tipo_alteracao="ADICIONADA", modificado_por_id=admin.id)
    if rascunho.modo == "QUIZ_CLASSICO":
        item = modelo(**comum, alternativa_a=payload["alternativas"][0], alternativa_b=payload["alternativas"][1], alternativa_c=payload["alternativas"][2], alternativa_d=payload["alternativas"][3], alternativa_correta=payload["alternativa_correta"], dificuldade=payload["dificuldade"])
        fonte_cls = FontePerguntaQuizRascunho
    else:
        item = modelo(**comum, resposta_numerica=int(payload["resposta_numerica"]), unidade=payload.get("unidade"), fonte=payload.get("fonte"), fonte_url=payload.get("fonte_url"), fonte_acessada_em=payload.get("fonte_acessada_em"), tema_editorial=payload.get("tema_editorial"), natureza_resposta=payload["natureza_resposta"], qualificacao_estimativa=payload.get("qualificacao_estimativa"))
        fonte_cls = FontePerguntaNemPatoRascunho
    item.fontes = [fonte_cls(ordem=i, **fonte) for i, fonte in enumerate(payload["referencias"], 1)]
    db.add(item); db.flush()
    anterior, nova = _avancar(rascunho, admin)
    _registrar_alteracao(db, rascunho, admin, "ADICAO", anterior, nova, pergunta=item, campos={"depois": _dados_pergunta(item)})
    registrar_auditoria_administrativa(db, admin, operacao="ADICIONAR_PERGUNTA_RASCUNHO", recurso_tipo="PERGUNTA_OFICIAL_RASCUNHO", recurso_id=item.id, resultado="SUCESSO", detalhes={"revisao": nova})
    db.flush(); return item, nova


def alterar_remocao(db, rascunho_id, pergunta_id, admin, revisao_esperada, *, restaurar):
    rascunho = _rascunho_editavel(db, rascunho_id, exigir_revisao(revisao_esperada))
    item = obter_pergunta(db, rascunho, pergunta_id)
    if item is None: raise _erro(404, "PERGUNTA_RASCUNHO_NAO_ENCONTRADA", "pergunta do rascunho não encontrada")
    if restaurar:
        if item.tipo_alteracao != "REMOVIDA": raise _erro(409, "PERGUNTA_NAO_REMOVIDA", "a pergunta não está removida")
        item.tipo_alteracao = "ADICIONADA" if item.pergunta_origem_id is None else "MODIFICADA"; tipo = "RESTAURACAO"
    else:
        if item.tipo_alteracao == "REMOVIDA": raise _erro(409, "PERGUNTA_JA_REMOVIDA", "a pergunta já está removida")
        item.tipo_alteracao = "REMOVIDA"; tipo = "REMOCAO"
    item.revisao += 1; item.modificado_por_id = admin.id
    anterior, nova = _avancar(rascunho, admin)
    _registrar_alteracao(db, rascunho, admin, tipo, anterior, nova, pergunta=item, campos={"tipo_alteracao": item.tipo_alteracao})
    registrar_auditoria_administrativa(db, admin, operacao=f"{tipo}_PERGUNTA_RASCUNHO", recurso_tipo="PERGUNTA_OFICIAL_RASCUNHO", recurso_id=item.id, resultado="SUCESSO", detalhes={"revisao": nova})
    db.flush(); return item, nova


def descartar_rascunho(db, rascunho_id, motivo, admin, revisao_esperada):
    revisao = exigir_revisao(revisao_esperada)
    rascunho = db.scalar(select(CatalogoOficialRascunho).where(CatalogoOficialRascunho.id == rascunho_id).with_for_update())
    if rascunho is None:
        raise _erro(404, "RASCUNHO_NAO_ENCONTRADO", "rascunho não encontrado")
    if rascunho.status not in {"EM_EDICAO", "EM_REVISAO"}:
        raise _erro(409, "RASCUNHO_NAO_DESCARTAVEL", "o estado atual não permite descarte")
    if rascunho.revisao != revisao:
        raise _erro(412, "REVISAO_DIVERGENTE", "o rascunho foi alterado por outra operação")
    if rascunho.status == "EM_REVISAO":
        from app.models import CicloRevisaoRascunho, TransicaoRascunhoEditorial
        ciclo = db.scalar(select(CicloRevisaoRascunho).where(
            CicloRevisaoRascunho.rascunho_id == rascunho.id,
            CicloRevisaoRascunho.estado == "EM_ANDAMENTO",
        ).with_for_update())
        if ciclo is not None:
            ciclo.estado = "INVALIDADO"
            ciclo.invalidado_em = datetime.now(timezone.utc)
            ciclo.motivo_invalidacao = motivo.strip()
        db.add(TransicaoRascunhoEditorial(
            rascunho_id=rascunho.id, estado_anterior="EM_REVISAO",
            estado_novo="DESCARTADO", revisao_conteudo=rascunho.revisao,
            justificativa=motivo.strip(), responsavel_id=admin.id,
            operacao="DESCARTAR_RASCUNHO",
        ))
    anterior, nova = _avancar(rascunho, admin)
    rascunho.status = "DESCARTADO"; rascunho.descartado_em = datetime.now(timezone.utc); rascunho.motivo_descarte = motivo.strip()
    _registrar_alteracao(db, rascunho, admin, "DESCARTE", anterior, nova, campos={"motivo": motivo})
    registrar_auditoria_administrativa(db, admin, operacao="DESCARTAR_RASCUNHO_CATALOGO", recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho.id, resultado="SUCESSO", detalhes={"revisao": nova})
    db.flush(); return rascunho


def listar_alteracoes(db, rascunho_id, *, pagina, limite):
    filtros = [AlteracaoRascunhoOficial.rascunho_id == rascunho_id]
    total = db.scalar(select(func.count()).select_from(AlteracaoRascunhoOficial).where(*filtros)) or 0
    itens = list(db.scalars(select(AlteracaoRascunhoOficial).where(*filtros).order_by(AlteracaoRascunhoOficial.ocorrida_em.desc(), AlteracaoRascunhoOficial.id).offset((pagina-1)*limite).limit(limite)))
    return itens, total, ceil(total/limite) if total else 0
