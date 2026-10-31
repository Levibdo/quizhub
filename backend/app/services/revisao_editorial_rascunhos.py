import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AchadoValidacaoRascunhoPersistido, AprovacaoRascunho,
    CatalogoOficialRascunho, CicloRevisaoRascunho, DecisaoAvisoValidacao,
    DecisaoRevisaoPergunta, FontePerguntaNemPatoRascunho,
    FontePerguntaQuizRascunho, ItemRevisaoPergunta, PerguntaNemPatoRascunho,
    PerguntaQuizRascunho, TransicaoRascunhoEditorial, Usuario,
    VerificacaoFonteRevisao,
)
from app.services.auditoria_administrativa import registrar_auditoria_administrativa
from app.services.validacao_rascunhos_oficiais import validar_rascunho_oficial

VERSAO_REGRAS = "C4.1-v1"


def _erro(status, codigo, mensagem):
    raise HTTPException(status, detail={"codigo": codigo, "mensagem": mensagem})


def _hash(objeto):
    return hashlib.sha256(json.dumps(objeto, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _rascunho_bloqueado(db, rascunho_id, revisao, estados):
    item = db.scalar(select(CatalogoOficialRascunho).where(CatalogoOficialRascunho.id == rascunho_id).with_for_update())
    if item is None: _erro(404, "RASCUNHO_NAO_ENCONTRADO", "rascunho não encontrado")
    if item.revisao != revisao: _erro(412, "REVISAO_DIVERGENTE", "a revisão de conteúdo divergiu")
    if item.status not in estados: _erro(409, "ESTADO_EDITORIAL_INCOMPATIVEL", "o estado do rascunho não permite a operação")
    return item


def _ciclo_ativo(db, rascunho_id, *, bloquear=False):
    q = select(CicloRevisaoRascunho).where(CicloRevisaoRascunho.rascunho_id == rascunho_id, CicloRevisaoRascunho.estado == "EM_ANDAMENTO")
    if bloquear: q = q.with_for_update()
    return db.scalar(q)


def _ciclo_para_consulta(db, rascunho_id):
    """Retorna o ciclo ativo ou, para histórico somente leitura, o mais recente."""
    ciclo = _ciclo_ativo(db, rascunho_id)
    if ciclo:
        return ciclo
    return db.scalar(
        select(CicloRevisaoRascunho)
        .where(CicloRevisaoRascunho.rascunho_id == rascunho_id)
        .order_by(CicloRevisaoRascunho.criado_em.desc(), CicloRevisaoRascunho.id.desc())
    )


def _transicao(db, rascunho, admin, novo, justificativa, operacao):
    db.add(TransicaoRascunhoEditorial(rascunho_id=rascunho.id, estado_anterior=rascunho.status, estado_novo=novo, revisao_conteudo=rascunho.revisao, justificativa=justificativa, responsavel_id=admin.id, operacao=operacao))
    rascunho.status = novo
    rascunho.modificado_por_id = admin.id
    rascunho.atualizado_em = datetime.now(timezone.utc)


def _publicaveis(db, rascunho):
    modelo = PerguntaQuizRascunho if rascunho.modo == "QUIZ_CLASSICO" else PerguntaNemPatoRascunho
    return list(db.scalars(select(modelo).options(selectinload(modelo.fontes)).where(modelo.rascunho_id == rascunho.id, modelo.tipo_alteracao != "REMOVIDA", modelo.ativa.is_(True)).order_by(modelo.ordem, modelo.id)))


def _validar_quantidade(perguntas, modo):
    """Valida o conjunto publicável, sem impor tamanho de lote editorial.

    Os tamanhos 400/100 continuam sendo validados pelo importador canônico
    completo. Um rascunho incremental precisa apenas produzir um catálogo não
    vazio; a integridade de cada pergunta é verificada pelo validador estrutural.
    """
    if not perguntas:
        _erro(422, "CATALOGO_SEM_PERGUNTAS", "o catálogo exige ao menos uma pergunta publicável")


def _alteradas_para_revisao(perguntas):
    return [p for p in perguntas if p.tipo_alteracao in {"ADICIONADA", "MODIFICADA"}]


def encaminhar_revisao(db: Session, rascunho_id: UUID, revisao: int, admin: Usuario):
    rascunho = _rascunho_bloqueado(db, rascunho_id, revisao, {"EM_EDICAO"})
    if _ciclo_ativo(db, rascunho.id): _erro(409, "CICLO_ATIVO_EXISTENTE", "já existe ciclo editorial ativo")
    relatorio = validar_rascunho_oficial(db, rascunho.id)
    if relatorio["resumo"]["erros"]: _erro(422, "VALIDACAO_COM_ERROS", "corrija os erros estruturais antes da revisão")
    perguntas = _publicaveis(db, rascunho); _validar_quantidade(perguntas, rascunho.modo)
    alteradas = _alteradas_para_revisao(perguntas)
    if not alteradas:
        _erro(409, "RASCUNHO_SEM_ALTERACOES_PUBLICAVEIS", "não existem perguntas novas ou modificadas para revisão")
    hash_validacao = _hash(relatorio)
    ciclo = CicloRevisaoRascunho(rascunho_id=rascunho.id, revisao_conteudo=rascunho.revisao, revisao_editorial=1, hash_validacao=hash_validacao, versao_regras=VERSAO_REGRAS, total_erros=relatorio["resumo"]["erros"], total_avisos=relatorio["resumo"]["avisos"], total_informacoes=relatorio["resumo"]["informacoes"], responsavel_id=admin.id)
    db.add(ciclo); db.flush()
    for achado in relatorio["achados"]:
        bruto = {k: str(v) if isinstance(v, UUID) else v for k, v in achado.items()}
        db.add(AchadoValidacaoRascunhoPersistido(ciclo_id=ciclo.id, codigo=achado["codigo"], severidade=achado["nivel"], pergunta_id=achado.get("pergunta_id"), id_editorial=achado.get("id_editorial"), campo=achado.get("campo"), mensagem=achado["mensagem"], recomendacao=achado.get("recomendacao"), fingerprint=_hash(bruto)))
    for pergunta in alteradas:
        db.add(ItemRevisaoPergunta(ciclo_id=ciclo.id, pergunta_quiz_id=pergunta.id if rascunho.modo == "QUIZ_CLASSICO" else None, pergunta_nem_pato_id=pergunta.id if rascunho.modo == "NEM_A_PATO" else None, id_editorial=pergunta.id_editorial, revisao_pergunta=pergunta.revisao))
    _transicao(db, rascunho, admin, "EM_REVISAO", "Validação estrutural concluída; revisão factual iniciada.", "ENCAMINHAR_REVISAO")
    registrar_auditoria_administrativa(db, admin, operacao="ENCAMINHAR_RASCUNHO_REVISAO", recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho.id, resultado="SUCESSO", detalhes={"ciclo_id": str(ciclo.id), "revisao": revisao, "hash_validacao": hash_validacao})
    db.flush(); return rascunho, ciclo


def obter_revisao(db, rascunho_id, administrador_id=None):
    rascunho = db.get(CatalogoOficialRascunho, rascunho_id)
    if not rascunho: return None
    ciclo = db.scalar(select(CicloRevisaoRascunho).where(CicloRevisaoRascunho.rascunho_id == rascunho_id).order_by(CicloRevisaoRascunho.criado_em.desc(), CicloRevisaoRascunho.id.desc()))
    contagens = {}
    if ciclo: contagens = dict(db.execute(select(ItemRevisaoPergunta.estado, func.count()).where(ItemRevisaoPergunta.ciclo_id == ciclo.id).group_by(ItemRevisaoPergunta.estado)).all())
    elegibilidade = avaliar_elegibilidade(db, rascunho, ciclo, administrador_id) if ciclo else {
        "elegivel_aprovacao": False,
        "impedimentos_aprovacao": [{"codigo": "CICLO_REVISAO_AUSENTE", "quantidade": 1, "mensagem": "Não existe ciclo editorial para este rascunho."}],
        "exige_justificativa_autorrevisao": False,
    }
    return {"rascunho_id": rascunho.id, "status": rascunho.status, "revisao_conteudo": rascunho.revisao, "ciclo_id": ciclo.id if ciclo else None, "estado_ciclo": ciclo.estado if ciclo else None, "revisao_editorial": ciclo.revisao_editorial if ciclo else None, "hash_validacao": ciclo.hash_validacao if ciclo else None, "contagens": contagens, **elegibilidade}


def listar_avisos(db, rascunho_id, *, pagina, limite, estado=None, severidade=None):
    ciclo = _ciclo_para_consulta(db, rascunho_id)
    if not ciclo:
        _erro(404, "CICLO_REVISAO_NAO_ENCONTRADO", "não existe ciclo editorial")
    filtros = [AchadoValidacaoRascunhoPersistido.ciclo_id == ciclo.id]
    if severidade:
        filtros.append(AchadoValidacaoRascunhoPersistido.severidade == severidade)
    decisao = DecisaoAvisoValidacao
    consulta = (
        select(AchadoValidacaoRascunhoPersistido, decisao)
        .outerjoin(decisao, (decisao.achado_id == AchadoValidacaoRascunhoPersistido.id) & (decisao.ciclo_id == ciclo.id))
        .where(*filtros)
    )
    if estado == "PENDENTE":
        consulta = consulta.where(decisao.id.is_(None))
    elif estado in {"ACEITO", "REJEITADO"}:
        consulta = consulta.where(decisao.decisao == estado)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    pendentes = db.scalar(
        select(func.count()).select_from(AchadoValidacaoRascunhoPersistido)
        .outerjoin(decisao, (decisao.achado_id == AchadoValidacaoRascunhoPersistido.id) & (decisao.ciclo_id == ciclo.id))
        .where(AchadoValidacaoRascunhoPersistido.ciclo_id == ciclo.id,
               AchadoValidacaoRascunhoPersistido.severidade == "AVISO", decisao.id.is_(None))
    ) or 0
    itens = db.execute(consulta.order_by(AchadoValidacaoRascunhoPersistido.id).offset((pagina - 1) * limite).limit(limite)).all()
    return ciclo, itens, total, pendentes


def listar_itens(db, rascunho_id, *, pagina, limite, estado=None):
    ciclo = _ciclo_para_consulta(db, rascunho_id)
    if not ciclo: _erro(404, "CICLO_REVISAO_NAO_ENCONTRADO", "não existe ciclo editorial")
    filtros = [ItemRevisaoPergunta.ciclo_id == ciclo.id]
    if estado: filtros.append(ItemRevisaoPergunta.estado == estado)
    total = db.scalar(select(func.count()).select_from(ItemRevisaoPergunta).where(*filtros)) or 0
    itens = list(db.scalars(select(ItemRevisaoPergunta).where(*filtros).order_by(ItemRevisaoPergunta.id_editorial).offset((pagina-1)*limite).limit(limite)))
    return ciclo, itens, total


def decidir_pergunta(db, rascunho_id, pergunta_id, revisao_conteudo, revisao_editorial, dados, admin):
    rascunho = _rascunho_bloqueado(db, rascunho_id, revisao_conteudo, {"EM_REVISAO"})
    ciclo = _ciclo_ativo(db, rascunho.id, bloquear=True)
    if not ciclo: _erro(409, "CICLO_ATIVO_NAO_ENCONTRADO", "não existe ciclo ativo")
    item = db.scalar(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id, ((ItemRevisaoPergunta.pergunta_quiz_id == pergunta_id) | (ItemRevisaoPergunta.pergunta_nem_pato_id == pergunta_id))).with_for_update())
    if not item: _erro(404, "ITEM_REVISAO_NAO_ENCONTRADO", "pergunta não integra o ciclo")
    if item.revisao_editorial != revisao_editorial: _erro(412, "REVISAO_EDITORIAL_DIVERGENTE", "a decisão foi alterada concorrentemente")
    anterior = item.revisao_editorial; item.revisao_editorial += 1; item.estado = dados["decisao"]; item.revisor_id = admin.id; item.atualizado_em = datetime.now(timezone.utc)
    ciclo.revisao_editorial += 1
    db.add(DecisaoRevisaoPergunta(item_id=item.id, decisao=dados["decisao"], justificativa=dados["justificativa"], relacao_fontes_resposta=dados.get("relacao_fontes_resposta"), responsavel_id=admin.id, revisao_anterior=anterior, revisao_nova=item.revisao_editorial))
    registrar_auditoria_administrativa(db, admin, operacao="DECIDIR_PERGUNTA_RASCUNHO", recurso_tipo="PERGUNTA_OFICIAL_RASCUNHO", recurso_id=pergunta_id, resultado="SUCESSO", detalhes={"decisao": dados["decisao"], "ciclo_id": str(ciclo.id)})
    db.flush(); return item, ciclo


def verificar_fonte(db, rascunho_id, pergunta_id, fonte_id, revisao_conteudo, revisao_editorial, dados, admin):
    rascunho = _rascunho_bloqueado(db, rascunho_id, revisao_conteudo, {"EM_REVISAO"}); ciclo = _ciclo_ativo(db, rascunho.id, bloquear=True)
    item = db.scalar(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id, ((ItemRevisaoPergunta.pergunta_quiz_id == pergunta_id) | (ItemRevisaoPergunta.pergunta_nem_pato_id == pergunta_id))).with_for_update()) if ciclo else None
    if not item: _erro(404, "ITEM_REVISAO_NAO_ENCONTRADO", "pergunta não integra o ciclo")
    if item.revisao_editorial != revisao_editorial: _erro(412, "REVISAO_EDITORIAL_DIVERGENTE", "a revisão editorial divergiu")
    cls = FontePerguntaQuizRascunho if item.pergunta_quiz_id else FontePerguntaNemPatoRascunho
    fonte = db.scalar(select(cls).where(cls.id == fonte_id, cls.pergunta_rascunho_id == pergunta_id))
    if not fonte: _erro(404, "FONTE_RASCUNHO_NAO_ENCONTRADA", "fonte não pertence à pergunta")
    if dados["resultado"] == "SUFICIENTE" and not dados.get("relacao_com_resposta"):
        _erro(422, "RELACAO_COM_RESPOSTA_OBRIGATORIA", "fonte suficiente exige explicação de como sustenta a resposta")
    snapshot = {"titulo": fonte.titulo, "url": fonte.url, "acessada_em": str(fonte.acessada_em)}
    db.add(VerificacaoFonteRevisao(item_id=item.id, fonte_quiz_id=fonte.id if item.pergunta_quiz_id else None, fonte_nem_pato_id=fonte.id if item.pergunta_nem_pato_id else None, fonte_titulo=fonte.titulo, fonte_url=fonte.url, fonte_acessada_em=str(fonte.acessada_em), fingerprint=_hash(snapshot), resultado=dados["resultado"], evidencia_documental=dados["evidencia_documental"], relacao_com_resposta=dados.get("relacao_com_resposta"), justificativa=dados.get("justificativa"), responsavel_id=admin.id))
    item.revisao_editorial += 1; ciclo.revisao_editorial += 1
    registrar_auditoria_administrativa(db, admin, operacao="VERIFICAR_FONTE_RASCUNHO", recurso_tipo="FONTE_PERGUNTA_RASCUNHO", recurso_id=fonte_id, resultado="SUCESSO", detalhes={"resultado": dados["resultado"], "ciclo_id": str(ciclo.id)})
    db.flush(); return item, ciclo


def decidir_aviso(db, rascunho_id, achado_id, revisao_conteudo, revisao_editorial, dados, admin):
    rascunho = _rascunho_bloqueado(db, rascunho_id, revisao_conteudo, {"EM_REVISAO"}); ciclo = _ciclo_ativo(db, rascunho.id, bloquear=True)
    if not ciclo or ciclo.revisao_editorial != revisao_editorial: _erro(412, "REVISAO_EDITORIAL_DIVERGENTE", "a revisão editorial divergiu")
    achado = db.scalar(select(AchadoValidacaoRascunhoPersistido).where(AchadoValidacaoRascunhoPersistido.id == achado_id, AchadoValidacaoRascunhoPersistido.ciclo_id == ciclo.id, AchadoValidacaoRascunhoPersistido.severidade == "AVISO"))
    if not achado: _erro(404, "AVISO_NAO_ENCONTRADO", "aviso não pertence ao ciclo")
    if db.scalar(select(DecisaoAvisoValidacao.id).where(DecisaoAvisoValidacao.ciclo_id == ciclo.id, DecisaoAvisoValidacao.achado_id == achado.id)): _erro(409, "AVISO_JA_DECIDIDO", "o aviso já possui decisão")
    db.add(DecisaoAvisoValidacao(ciclo_id=ciclo.id, achado_id=achado.id, decisao=dados["decisao"], justificativa=dados["justificativa"], responsavel_id=admin.id)); ciclo.revisao_editorial += 1
    db.flush(); return ciclo


def _invalidar(db, rascunho, ciclo, admin, justificativa, operacao):
    agora = datetime.now(timezone.utc); ciclo.estado = "INVALIDADO"; ciclo.invalidado_em = agora; ciclo.motivo_invalidacao = justificativa
    aprovacoes = list(db.scalars(select(AprovacaoRascunho).where(AprovacaoRascunho.rascunho_id == rascunho.id, AprovacaoRascunho.valida.is_(True)).with_for_update()))
    for aprovacao in aprovacoes: aprovacao.valida = False; aprovacao.invalidada_em = agora; aprovacao.motivo_invalidacao = justificativa
    _transicao(db, rascunho, admin, "EM_EDICAO", justificativa, operacao)


def avaliar_elegibilidade(db, rascunho, ciclo, administrador_id=None):
    impedimentos = []
    def impedir(codigo, quantidade, mensagem):
        impedimentos.append({"codigo": codigo, "quantidade": quantidade, "mensagem": mensagem})

    if rascunho.status != "EM_REVISAO" or ciclo.estado != "EM_ANDAMENTO":
        impedir("ESTADO_EDITORIAL_INCOMPATIVEL", 1, "O rascunho não está em revisão editorial ativa.")
    if ciclo.revisao_conteudo != rascunho.revisao:
        impedir("REVISAO_CONTEUDO_DIVERGENTE", 1, "A revisão do conteúdo diverge do ciclo editorial.")

    relatorio = validar_rascunho_oficial(db, rascunho.id)
    if _hash(relatorio) != ciclo.hash_validacao or relatorio["resumo"]["erros"]:
        impedir("VALIDACAO_DIVERGENTE", relatorio["resumo"]["erros"], "A validação atual diverge do snapshot do ciclo ou contém erros.")

    perguntas = _publicaveis(db, rascunho)
    try:
        _validar_quantidade(perguntas, rascunho.modo)
    except HTTPException as erro:
        detalhe = erro.detail if isinstance(erro.detail, dict) else {}
        impedir(detalhe.get("codigo", "CATALOGO_INVALIDO"), 1, detalhe.get("mensagem", str(erro.detail)))

    alteradas = _alteradas_para_revisao(perguntas)
    itens = list(db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id)))
    nao_aprovadas = sum(item.estado != "APROVADA" for item in itens)
    if len(itens) != len(alteradas) or nao_aprovadas:
        impedir("PERGUNTAS_ALTERADAS_NAO_APROVADAS", max(abs(len(alteradas) - len(itens)), nao_aprovadas), "Todas as perguntas novas ou modificadas precisam estar aprovadas.")

    ids_com_fonte_suficiente = set(db.scalars(
        select(VerificacaoFonteRevisao.item_id).where(
            VerificacaoFonteRevisao.item_id.in_([item.id for item in itens]),
            VerificacaoFonteRevisao.resultado == "SUFICIENTE",
        ).distinct()
    )) if itens else set()
    sem_fonte = sum(item.id not in ids_com_fonte_suficiente for item in itens)
    if sem_fonte:
        impedir("FONTE_SUFICIENTE_AUSENTE", sem_fonte, "Há perguntas sem ao menos uma fonte documental suficiente.")

    total_avisos = db.scalar(select(func.count()).select_from(AchadoValidacaoRascunhoPersistido).where(
        AchadoValidacaoRascunhoPersistido.ciclo_id == ciclo.id,
        AchadoValidacaoRascunhoPersistido.severidade == "AVISO",
    )) or 0
    decisoes = list(db.scalars(select(DecisaoAvisoValidacao).where(DecisaoAvisoValidacao.ciclo_id == ciclo.id)))
    pendentes = total_avisos - len(decisoes)
    rejeitados = sum(decisao.decisao == "REJEITADO" for decisao in decisoes)
    if pendentes:
        impedir("AVISOS_PENDENTES", pendentes, "Existem avisos aguardando decisão editorial.")
    if rejeitados:
        impedir("AVISOS_REJEITADOS", rejeitados, "Existem avisos rejeitados no ciclo atual.")

    autorrevisao = bool(administrador_id and any(item.revisor_id == administrador_id for item in itens))
    return {
        "elegivel_aprovacao": not impedimentos,
        "impedimentos_aprovacao": impedimentos,
        "exige_justificativa_autorrevisao": autorrevisao,
    }


def devolver_edicao(db, rascunho_id, revisao, justificativa, admin, perguntas=None, revisao_editorial=None):
    rascunho = _rascunho_bloqueado(db, rascunho_id, revisao, {"EM_REVISAO"}); ciclo = _ciclo_ativo(db, rascunho.id, bloquear=True)
    if not ciclo: _erro(409, "CICLO_ATIVO_NAO_ENCONTRADO", "não existe ciclo ativo")
    if revisao_editorial is None: _erro(428, "REVISAO_EDITORIAL_OBRIGATORIA", "a revisão editorial é obrigatória")
    if ciclo.revisao_editorial != revisao_editorial: _erro(412, "REVISAO_EDITORIAL_DIVERGENTE", "a revisão editorial divergiu")
    if perguntas:
        itens = list(db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id, ((ItemRevisaoPergunta.pergunta_quiz_id.in_(perguntas)) | (ItemRevisaoPergunta.pergunta_nem_pato_id.in_(perguntas)))).with_for_update()))
        if len(itens) != len(set(perguntas)): _erro(404, "PERGUNTA_REVISAO_NAO_ENCONTRADA", "uma pergunta não integra o ciclo")
        for item in itens:
            anterior=item.revisao_editorial; item.revisao_editorial += 1; item.estado="CORRECAO_SOLICITADA"; item.revisor_id=admin.id
            db.add(DecisaoRevisaoPergunta(item_id=item.id, decisao="CORRECAO_SOLICITADA", justificativa=justificativa, responsavel_id=admin.id, revisao_anterior=anterior, revisao_nova=item.revisao_editorial))
    _invalidar(db, rascunho, ciclo, admin, justificativa, "SOLICITAR_CORRECAO" if perguntas else "DEVOLVER_EDICAO")
    registrar_auditoria_administrativa(db, admin, operacao="DEVOLVER_RASCUNHO_EDICAO", recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho.id, resultado="SUCESSO", detalhes={"ciclo_id": str(ciclo.id), "perguntas": len(perguntas or [])})
    db.flush(); return rascunho, ciclo


def aprovar(db, rascunho_id, revisao, revisao_editorial, dados, admin):
    rascunho = _rascunho_bloqueado(db, rascunho_id, revisao, {"EM_REVISAO"}); ciclo = _ciclo_ativo(db, rascunho.id, bloquear=True)
    if not ciclo or ciclo.revisao_editorial != revisao_editorial: _erro(412, "REVISAO_EDITORIAL_DIVERGENTE", "a revisão editorial divergiu")
    if not dados["confirmacao_explicita"]: _erro(422, "CONFIRMACAO_APROVACAO_OBRIGATORIA", "a aprovação exige confirmação explícita")
    politica = avaliar_elegibilidade(db, rascunho, ciclo, admin.id)
    if not politica["elegivel_aprovacao"]:
        primeiro = politica["impedimentos_aprovacao"][0]
        status = 412 if primeiro["codigo"] in {"VALIDACAO_DIVERGENTE", "REVISAO_CONTEUDO_DIVERGENTE"} else 422
        _erro(status, primeiro["codigo"], primeiro["mensagem"])
    itens = list(db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id).with_for_update()))
    autorrevisao = politica["exige_justificativa_autorrevisao"]
    if autorrevisao and (not dados.get("justificativa_autorrevisao") or len(dados["justificativa_autorrevisao"].strip()) < 20): _erro(422, "JUSTIFICATIVA_AUTORREVISAO_OBRIGATORIA", "autorrevisão exige justificativa reforçada")
    aprovacao = AprovacaoRascunho(rascunho_id=rascunho.id, ciclo_id=ciclo.id, revisao_conteudo=rascunho.revisao, hash_validacao=ciclo.hash_validacao, responsavel_id=admin.id, confirmacao_explicita=True, autorrevisao=autorrevisao, justificativa_autorrevisao=dados.get("justificativa_autorrevisao"), valida=True)
    db.add(aprovacao); ciclo.estado="CONCLUIDO"; ciclo.concluido_em=datetime.now(timezone.utc)
    _transicao(db, rascunho, admin, "APROVADO", "Revisão factual integral concluída.", "APROVAR_RASCUNHO")
    registrar_auditoria_administrativa(db, admin, operacao="APROVAR_RASCUNHO", recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho.id, resultado="SUCESSO", detalhes={"ciclo_id": str(ciclo.id), "autorrevisao": autorrevisao})
    db.flush(); return rascunho, ciclo, aprovacao


def reabrir(db, rascunho_id, revisao, justificativa, admin):
    rascunho = _rascunho_bloqueado(db, rascunho_id, revisao, {"APROVADO"})
    ciclo = db.scalar(select(CicloRevisaoRascunho).where(CicloRevisaoRascunho.rascunho_id == rascunho.id, CicloRevisaoRascunho.estado == "CONCLUIDO").order_by(CicloRevisaoRascunho.concluido_em.desc()).with_for_update())
    if not ciclo: _erro(409, "APROVACAO_INTEGRA_NAO_ENCONTRADA", "não existe aprovação para reabrir")
    _invalidar(db, rascunho, ciclo, admin, justificativa, "REABRIR_RASCUNHO")
    registrar_auditoria_administrativa(db, admin, operacao="REABRIR_RASCUNHO", recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho.id, resultado="SUCESSO", detalhes={"ciclo_id": str(ciclo.id)})
    db.flush(); return rascunho, ciclo
