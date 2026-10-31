import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AprovacaoRascunho, CatalogoOficial, CatalogoOficialRascunho,
    FontePerguntaNemPatoOficial, FontePerguntaOficial, Pergunta,
    PerguntaNemPato, PerguntaNemPatoRascunho, PerguntaQuizRascunho,
    TransicaoRascunhoEditorial, Usuario,
)
from app.services.auditoria_administrativa import registrar_auditoria_administrativa
from app.services.validacao_rascunhos_oficiais import validar_rascunho_oficial


def _falhar(status, codigo, mensagem):
    raise HTTPException(status, {"codigo": codigo, "mensagem": mensagem})


def _conteudo(perguntas):
    campos = ("id_editorial", "categoria_id", "ordem", "enunciado", "alternativa_a", "alternativa_b", "alternativa_c", "alternativa_d", "alternativa_correta", "dificuldade", "resposta_numerica", "unidade", "explicacao", "fonte", "fonte_url", "fonte_acessada_em", "tema_editorial", "natureza_resposta", "qualificacao_estimativa", "ativa")
    return [{k: str(getattr(p, k)) if getattr(p, k, None) is not None else None for k in campos if hasattr(p, k)} | {"fontes": [{"ordem": f.ordem, "titulo": f.titulo, "url": f.url, "acessada_em": str(f.acessada_em)} for f in p.fontes]} for p in perguntas]


def _antes_de_ativar(_db: Session, _novo: CatalogoOficial) -> None:
    """Ponto interno para observabilidade/teste de rollback transacional."""


def publicar_rascunho(db: Session, rascunho_id: UUID, revisao: int, admin: Usuario, justificativa: str):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("LOCK TABLE catalogos_oficiais IN SHARE ROW EXCLUSIVE MODE"))
    r = db.scalar(select(CatalogoOficialRascunho).where(CatalogoOficialRascunho.id == rascunho_id).with_for_update())
    if not r: _falhar(404, "RASCUNHO_NAO_ENCONTRADO", "rascunho não encontrado")
    if r.revisao != revisao: _falhar(412, "REVISAO_DIVERGENTE", "a revisão de conteúdo divergiu")
    if r.status != "APROVADO": _falhar(409, "RASCUNHO_NAO_APROVADO", "somente rascunho aprovado pode ser publicado")
    aprovacao = db.scalar(select(AprovacaoRascunho).where(AprovacaoRascunho.rascunho_id == r.id, AprovacaoRascunho.revisao_conteudo == r.revisao, AprovacaoRascunho.valida.is_(True)).with_for_update())
    if not aprovacao: _falhar(409, "APROVACAO_VALIDA_AUSENTE", "a aprovação editorial válida não foi encontrada")
    relatorio = validar_rascunho_oficial(db, r.id)
    if relatorio["resumo"]["erros"]: _falhar(422, "VALIDACAO_COM_ERROS", "o catálogo contém erros estruturais")
    hash_validacao = hashlib.sha256(json.dumps(relatorio, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    if hash_validacao != aprovacao.hash_validacao:
        _falhar(409, "APROVACAO_DESATUALIZADA", "o conteúdo validado diverge da aprovação editorial")
    modelo = PerguntaQuizRascunho if r.modo == "QUIZ_CLASSICO" else PerguntaNemPatoRascunho
    perguntas = list(db.scalars(select(modelo).options(selectinload(modelo.fontes)).where(modelo.rascunho_id == r.id, modelo.tipo_alteracao != "REMOVIDA", modelo.ativa.is_(True)).order_by(modelo.ordem, modelo.id)))
    if not perguntas: _falhar(422, "CATALOGO_SEM_PERGUNTAS", "o catálogo exige ao menos uma pergunta")
    ativo = db.scalar(select(CatalogoOficial).where(CatalogoOficial.modo == r.modo, CatalogoOficial.status == "ATIVO").with_for_update())
    if ativo and ativo.id != r.catalogo_origem_id: _falhar(409, "BASE_CATALOGO_DESATUALIZADA", "o rascunho não deriva da versão ativa atual")
    versao = (db.scalar(select(func.max(CatalogoOficial.versao)).where(CatalogoOficial.catalogo_id == r.catalogo_id)) or 0) + 1
    agora = datetime.now(timezone.utc)
    novo = CatalogoOficial(catalogo_id=r.catalogo_id, versao=versao, modo=r.modo, status="PREPARADO", sha256=hashlib.sha256(json.dumps(_conteudo(perguntas), sort_keys=True, ensure_ascii=False).encode()).hexdigest())
    db.add(novo); db.flush()
    if r.modo == "QUIZ_CLASSICO":
        proximo = (db.scalar(select(func.max(Pergunta.id))) or 0) + 1
        for p in perguntas:
            q = Pergunta(id=proximo, categoria_id=p.categoria_id, enunciado=p.enunciado, alternativa_a=p.alternativa_a, alternativa_b=p.alternativa_b, alternativa_c=p.alternativa_c, alternativa_d=p.alternativa_d, alternativa_correta=p.alternativa_correta, explicacao=p.explicacao, dificuldade=p.dificuldade, ativa=True, origem="OFICIAL", catalogo_oficial_id=novo.id, id_editorial=p.id_editorial); proximo += 1
            q.fontes_editoriais = [FontePerguntaOficial(ordem=f.ordem, titulo=f.titulo, url=f.url, acessada_em=f.acessada_em) for f in p.fontes]; db.add(q)
    else:
        for p in perguntas:
            q = PerguntaNemPato(categoria_id=p.categoria_id, enunciado=p.enunciado, resposta_numerica=p.resposta_numerica, unidade=p.unidade, explicacao=p.explicacao, fonte=p.fonte, fonte_url=p.fonte_url, fonte_acessada_em=p.fonte_acessada_em, ativa=True, origem="OFICIAL", catalogo_oficial_id=novo.id, id_editorial=p.id_editorial, tema_editorial=p.tema_editorial, natureza_resposta=p.natureza_resposta, qualificacao_estimativa=p.qualificacao_estimativa)
            q.fontes_editoriais = [FontePerguntaNemPatoOficial(ordem=f.ordem, titulo=f.titulo, url=f.url, acessada_em=f.acessada_em) for f in p.fontes]; db.add(q)
    _antes_de_ativar(db, novo)
    if ativo:
        ativo.status, ativo.arquivado_em = "ARQUIVADO", agora
        db.flush()
    novo.status, novo.ativado_em = "ATIVO", agora
    db.add(TransicaoRascunhoEditorial(rascunho_id=r.id, estado_anterior=r.status, estado_novo="PUBLICADO", revisao_conteudo=r.revisao, justificativa=justificativa, responsavel_id=admin.id, operacao="PUBLICAR_RASCUNHO"))
    r.status, r.catalogo_publicado_id, r.publicado_em, r.atualizado_em = "PUBLICADO", novo.id, agora, agora
    registrar_auditoria_administrativa(db, admin, operacao="PUBLICAR_RASCUNHO", recurso_tipo="CATALOGO_OFICIAL", recurso_id=novo.id, resultado="SUCESSO", catalogo_id=novo.catalogo_id, catalogo_versao=novo.versao, detalhes={"rascunho_id": str(r.id), "total_perguntas": len(perguntas)})
    db.flush()
    return r, novo, len(perguntas)
