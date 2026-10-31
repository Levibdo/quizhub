from datetime import datetime, timezone
import hashlib
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Path, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db, get_session_factory
from app.models import AuditoriaAdministrativa, CatalogoOficial, Usuario
from app.schemas.admin import (
    AuditoriaAdministrativaPublica,
    CatalogoAdministrativo,
    CriarCatalogoInicial,
    DashboardAdministrativo,
    ListaCatalogosOficiais,
    OpcoesPerguntasOficiais,
    PaginaPerguntasOficiais,
    PerguntaOficialDetalhe,
    PaginaAuditoriaAdministrativa,
    ReativarCatalogoEntrada,
    ReativacaoCatalogoPublica,
    ResumoAdministrativo,
    TokenCsrfAdministrativo,
)
from app.schemas.rascunhos_oficiais import (
    AlteracaoRascunhoPublica, CriarRascunho, DescartarRascunho,
    PaginaAlteracoesRascunho, PaginaPerguntasRascunho, PaginaRascunhos,
    PerguntaNemPatoRascunhoEntrada, PerguntaQuizRascunhoEntrada,
    PerguntaRascunhoDetalhe, RascunhoResumo, ValidacaoRascunhoOficial,
)
from app.schemas.revisao_editorial import (
    AprovarRascunhoEntrada, DecisaoAvisoEntrada, DecisaoPerguntaEntrada,
    MotivoEditorial, SolicitarCorrecaoEntrada, VerificacaoFonteEntrada,
)
from app.services.dashboard_administrativo import obter_dashboard_administrativo
from app.services.consulta_catalogos_oficiais import consultar_catalogos_oficiais
from app.services.consulta_perguntas_oficiais import (
    consultar_perguntas_oficiais,
    obter_pergunta_oficial,
    opcoes_perguntas_oficiais,
)
from app.services.consulta_auditoria_administrativa import (
    consultar_auditoria_administrativa,
)
from app.services.seguranca_administrativa import sanitizar_detalhes_auditoria
from app.services.idempotencia_administrativa import executar_operacao_idempotente
from app.services.auditoria_administrativa import registrar_auditoria_administrativa
from app.services.rascunhos_catalogos_oficiais import (
    adicionar_pergunta, alterar_remocao, criar_rascunho, descartar_rascunho,
    listar_alteracoes, listar_perguntas, listar_rascunhos, obter_pergunta,
    obter_rascunho, salvar_pergunta,
)
from app.services.validacao_rascunhos_oficiais import validar_rascunho_oficial
from app.services.publicacao_incremental_catalogos import publicar_rascunho
from app.services.reativacao_catalogos_oficiais import reativar_catalogo_oficial
from app.services.revisao_editorial_rascunhos import (
    aprovar, decidir_aviso, decidir_pergunta, devolver_edicao,
    encaminhar_revisao, listar_avisos, listar_itens, obter_revisao, reabrir,
    verificar_fonte,
)
from app.security import (
    CSRF_COOKIE_NAME,
    CSRF_DURACAO,
    JWT_COOKIE_NAME,
    cookie_secure,
    criar_token_csrf,
    exigir_admin,
    exigir_csrf_admin,
)


router = APIRouter(prefix="/admin", tags=["Administração"])


def _serializar_auditoria(item) -> AuditoriaAdministrativaPublica:
    return AuditoriaAdministrativaPublica(
        id=item.id,
        administrador_id=item.administrador_id,
        administrador_nome=item.administrador.nome,
        ocorrida_em=item.ocorrida_em,
        operacao=item.operacao,
        recurso_tipo=item.recurso_tipo,
        recurso_id=item.recurso_id,
        resultado=item.resultado,
        catalogo_id=item.catalogo_id,
        catalogo_versao=item.catalogo_versao,
        detalhes=sanitizar_detalhes_auditoria(item.detalhes),
    )


@router.get("/csrf", response_model=TokenCsrfAdministrativo)
def emitir_token_csrf_administrativo(
    response: Response,
    token_sessao: str = Cookie(alias=JWT_COOKIE_NAME),
    administrador: Usuario = Depends(exigir_admin),
):
    token = criar_token_csrf(administrador.id, token_sessao)
    duracao = int(CSRF_DURACAO.total_seconds())
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=duracao,
        httponly=False,
        secure=cookie_secure(),
        samesite="strict",
        path="/api/v1",
    )
    return TokenCsrfAdministrativo(token=token, expira_em_segundos=duracao)


@router.get("/resumo", response_model=ResumoAdministrativo)
def resumo_administrativo(
    limite_auditoria: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    catalogos = list(
        db.scalars(
            select(CatalogoOficial).order_by(
                CatalogoOficial.modo,
                CatalogoOficial.versao.desc(),
            )
        )
    )
    auditorias = list(
        db.scalars(
            select(AuditoriaAdministrativa)
            .options(joinedload(AuditoriaAdministrativa.administrador))
            .order_by(AuditoriaAdministrativa.ocorrida_em.desc())
            .limit(limite_auditoria)
        )
    )
    return ResumoAdministrativo(
        catalogos=[CatalogoAdministrativo.model_validate(item) for item in catalogos],
        auditorias=[_serializar_auditoria(item) for item in auditorias],
    )


def _serializar_dashboard(dados: dict) -> DashboardAdministrativo:
    return DashboardAdministrativo(
        indicadores=dados["indicadores"],
        temporada_ativa=dados["temporada_ativa"],
        catalogos=[
            CatalogoAdministrativo.model_validate(item)
            for item in dados["catalogos"]
        ],
        auditorias=[
            _serializar_auditoria(item) for item in dados["auditorias"]
        ],
    )


@router.get("/dashboard", response_model=DashboardAdministrativo)
def dashboard_administrativo(
    limite_auditoria: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    return _serializar_dashboard(obter_dashboard_administrativo(
        db, limite_auditoria=limite_auditoria
    ))


@router.get("/catalogos", response_model=ListaCatalogosOficiais)
def listar_catalogos_oficiais(
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    return ListaCatalogosOficiais(
        catalogos=consultar_catalogos_oficiais(db),
    )


@router.post("/catalogos", response_model=CatalogoAdministrativo, status_code=201)
def criar_catalogo_inicial(
    dados: CriarCatalogoInicial,
    chave: str | None = Header(None, alias="Idempotency-Key"),
    admin: Usuario = Depends(exigir_csrf_admin),
):
    pedido = dados.model_dump(mode="json")

    def executar(db: Session):
        existente = db.scalar(select(CatalogoOficial.id).where(
            CatalogoOficial.modo == dados.modo,
        ).limit(1))
        if existente is not None:
            raise HTTPException(
                status_code=409,
                detail={"codigo": "CATALOGO_INICIAL_JA_EXISTE", "mensagem": "já existe uma versão oficial para este modo"},
            )
        item = CatalogoOficial(
            catalogo_id=dados.catalogo_id,
            versao=1,
            modo=dados.modo,
            status="ATIVO",
            sha256=hashlib.sha256(b"").hexdigest(),
            ativado_em=datetime.now(timezone.utc),
        )
        db.add(item)
        db.flush()
        registrar_auditoria_administrativa(
            db, db.get(Usuario, admin.id), operacao="CRIAR_CATALOGO_INICIAL",
            recurso_tipo="CATALOGO_OFICIAL", recurso_id=item.id,
            catalogo_id=item.catalogo_id, catalogo_versao=1,
            resultado="SUCESSO", detalhes={"modo": item.modo, "perguntas": 0},
        )
        return 201, {"id": str(item.id)}

    resultado = _executar_idempotente(
        admin=admin, tipo="CRIAR_CATALOGO_INICIAL", recurso_tipo="CATALOGO_OFICIAL",
        recurso_id=dados.modo, chave=chave, pedido=pedido, executar=executar,
    )
    with get_session_factory()() as db:
        return CatalogoAdministrativo.model_validate(
            db.get(CatalogoOficial, UUID(resultado.resposta["id"]))
        )


@router.post("/catalogos/{catalogo_id}/reativar", response_model=ReativacaoCatalogoPublica)
def reativar_catalogo_admin(
    catalogo_id: UUID,
    dados: ReativarCatalogoEntrada,
    if_match: str | None = Header(None, alias="If-Match"),
    chave: str | None = Header(None, alias="Idempotency-Key"),
    admin: Usuario = Depends(exigir_csrf_admin),
):
    ativo_esperado_id = _catalogo_ativo_if_match(if_match)
    pedido = dados.model_dump(mode="json") | {"ativo_esperado_id": str(ativo_esperado_id)}

    def executar(db: Session):
        resposta = reativar_catalogo_oficial(
            db, catalogo_id, ativo_esperado_id,
            db.get(Usuario, admin.id), dados.justificativa,
        )
        return 200, resposta

    resultado = _executar_idempotente(
        admin=admin, tipo="REATIVAR_CATALOGO_OFICIAL",
        recurso_tipo="CATALOGO_OFICIAL", recurso_id=catalogo_id,
        chave=chave, pedido=pedido, executar=executar,
    )
    return ReativacaoCatalogoPublica(**resultado.resposta)


@router.get("/perguntas/opcoes", response_model=OpcoesPerguntasOficiais)
def listar_opcoes_perguntas_oficiais(
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    return OpcoesPerguntasOficiais(**opcoes_perguntas_oficiais(db))


@router.get("/perguntas", response_model=PaginaPerguntasOficiais)
def listar_perguntas_oficiais(
    pagina: int = Query(default=1, ge=1),
    limite: int = Query(default=20, ge=1, le=100),
    modo: Literal["QUIZ_CLASSICO", "NEM_A_PATO"] | None = None,
    catalogo_id: UUID | None = None,
    versao: int | None = Query(default=None, ge=1),
    categoria_id: UUID | None = None,
    ativa: bool | None = None,
    dificuldade: Literal["FACIL", "MEDIA", "DIFICIL"] | None = None,
    busca: str | None = Query(default=None, min_length=1, max_length=300),
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    return PaginaPerguntasOficiais(**consultar_perguntas_oficiais(
        db,
        pagina=pagina,
        limite=limite,
        modo=modo,
        catalogo_id=catalogo_id,
        versao=versao,
        categoria_id=categoria_id,
        ativa=ativa,
        dificuldade=dificuldade,
        busca=busca.strip() if busca else None,
    ))


@router.get(
    "/perguntas/{modo}/{pergunta_id}",
    response_model=PerguntaOficialDetalhe,
)
def detalhar_pergunta_oficial(
    modo: Literal["QUIZ_CLASSICO", "NEM_A_PATO"],
    pergunta_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    pergunta = obter_pergunta_oficial(
        db, modo=modo, pergunta_id=pergunta_id,
    )
    if pergunta is None:
        raise HTTPException(status_code=404, detail="pergunta oficial não encontrada")
    return PerguntaOficialDetalhe(**pergunta)


def _resumo_rascunho(db, item):
    from app.models import PerguntaNemPatoRascunho, PerguntaQuizRascunho
    modelo = PerguntaQuizRascunho if item.modo == "QUIZ_CLASSICO" else PerguntaNemPatoRascunho
    contagens = dict(db.execute(
        select(modelo.tipo_alteracao, func.count(modelo.id))
        .where(modelo.rascunho_id == item.id)
        .group_by(modelo.tipo_alteracao)
    ).all())
    total = sum(contagens.values())
    return RascunhoResumo.model_validate(item).model_copy(update={
        "total_perguntas": total,
        "adicionadas": contagens.get("ADICIONADA", 0),
        "modificadas": contagens.get("MODIFICADA", 0),
        "removidas": contagens.get("REMOVIDA", 0),
    })


def _detalhe_pergunta(item):
    alternativas = None
    if hasattr(item, "alternativa_a"):
        alternativas = [item.alternativa_a, item.alternativa_b, item.alternativa_c, item.alternativa_d]
    return PerguntaRascunhoDetalhe(
        id=item.id, id_editorial=item.id_editorial,
        categoria_id=item.categoria_id,
        categoria_slug=item.categoria_slug_snapshot,
        categoria_nome=item.categoria_nome_snapshot,
        ordem=item.ordem, enunciado=item.enunciado, ativa=item.ativa,
        tipo_alteracao=item.tipo_alteracao, revisao=item.revisao,
        dificuldade=getattr(item, "dificuldade", None),
        explicacao=item.explicacao, alternativas=alternativas,
        alternativa_correta=getattr(item, "alternativa_correta", None),
        resposta_numerica=(str(item.resposta_numerica) if hasattr(item, "resposta_numerica") else None),
        unidade=getattr(item, "unidade", None), fonte=getattr(item, "fonte", None),
        fonte_url=getattr(item, "fonte_url", None),
        fonte_acessada_em=getattr(item, "fonte_acessada_em", None),
        tema_editorial=getattr(item, "tema_editorial", None),
        natureza_resposta=getattr(item, "natureza_resposta", None),
        qualificacao_estimativa=getattr(item, "qualificacao_estimativa", None),
        referencias=[{"id": f.id, "titulo": f.titulo, "url": f.url, "acessada_em": f.acessada_em} for f in item.fontes],
    )


def _revisao_if_match(valor: str | None) -> int:
    if valor is None:
        raise HTTPException(status_code=428, detail={"codigo": "REVISAO_OBRIGATORIA", "mensagem": "If-Match é obrigatório"})
    try:
        return int(valor.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=422, detail={"codigo": "REVISAO_INVALIDA", "mensagem": "If-Match deve conter uma revisão inteira"}) from None


def _catalogo_ativo_if_match(valor: str | None) -> UUID:
    if valor is None:
        raise HTTPException(status_code=428, detail={"codigo": "VERSAO_ATIVA_OBRIGATORIA", "mensagem": "If-Match é obrigatório"})
    try:
        return UUID(valor.strip().strip('"'))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail={"codigo": "VERSAO_ATIVA_INVALIDA", "mensagem": "If-Match deve conter o UUID da versão ativa"}) from None


def _executar_idempotente(*, admin, tipo, recurso_tipo, recurso_id, chave, pedido, executar):
    return executar_operacao_idempotente(
        get_session_factory(), administrador_id=admin.id, tipo_operacao=tipo,
        recurso_tipo=recurso_tipo, recurso_id=recurso_id,
        chave_idempotencia=chave, pedido=pedido, executar=executar,
    )


def _revisao_editorial(cabecalho: str | None) -> int:
    if cabecalho is None:
        raise HTTPException(428, detail={"codigo": "REVISAO_EDITORIAL_OBRIGATORIA", "mensagem": "X-Editorial-Revision é obrigatório"})
    try:
        valor = int(cabecalho.strip().strip('"'))
    except ValueError:
        raise HTTPException(422, detail={"codigo": "REVISAO_EDITORIAL_INVALIDA", "mensagem": "a revisão editorial deve ser inteira"}) from None
    if valor < 1:
        raise HTTPException(422, detail={"codigo": "REVISAO_EDITORIAL_INVALIDA", "mensagem": "a revisão editorial deve ser positiva"})
    return valor


@router.get("/catalogos/rascunhos", response_model=PaginaRascunhos)
def listar_rascunhos_admin(pagina: int = Query(1, ge=1), limite: int = Query(20, ge=1, le=100), modo: Literal["QUIZ_CLASSICO", "NEM_A_PATO"] | None = None, status_rascunho: str | None = None, db: Session = Depends(get_db), _admin: Usuario = Depends(exigir_admin)):
    itens, total, paginas = listar_rascunhos(db, pagina=pagina, limite=limite, modo=modo, status_rascunho=status_rascunho)
    return PaginaRascunhos(itens=[_resumo_rascunho(db, i) for i in itens], pagina=pagina, limite=limite, total=total, total_paginas=paginas)


@router.get("/catalogos/rascunhos/{rascunho_id}", response_model=RascunhoResumo)
def consultar_rascunho_admin(rascunho_id: UUID, db: Session = Depends(get_db), _admin: Usuario = Depends(exigir_admin)):
    item = obter_rascunho(db, rascunho_id)
    if item is None: raise HTTPException(404, "rascunho não encontrado")
    return _resumo_rascunho(db, item)


@router.get(
    "/catalogos/rascunhos/{rascunho_id}/validacao",
    response_model=ValidacaoRascunhoOficial,
)
def validar_rascunho_admin(
    rascunho_id: UUID,
    db: Session = Depends(get_db),
    _admin: Usuario = Depends(exigir_admin),
):
    resultado = validar_rascunho_oficial(db, rascunho_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail="rascunho não encontrado")
    return ValidacaoRascunhoOficial(**resultado)


@router.post("/catalogos/{catalogo_id}/rascunhos", response_model=RascunhoResumo, status_code=201)
def criar_rascunho_admin(catalogo_id: UUID, dados: CriarRascunho, chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    pedido = dados.model_dump(mode="json")
    def executar(db):
        item = criar_rascunho(db, catalogo_id, dados.nome, db.get(Usuario, admin.id))
        return 201, {"id": str(item.id)}
    resultado = _executar_idempotente(admin=admin, tipo="CRIAR_RASCUNHO_CATALOGO", recurso_tipo="CATALOGO_OFICIAL", recurso_id=catalogo_id, chave=chave, pedido=pedido, executar=executar)
    with get_session_factory()() as db:
        item = obter_rascunho(db, UUID(resultado.resposta["id"]))
        return _resumo_rascunho(db, item)


@router.get("/catalogos/rascunhos/{rascunho_id}/perguntas", response_model=PaginaPerguntasRascunho)
def listar_perguntas_rascunho_admin(rascunho_id: UUID, pagina: int = Query(1, ge=1), limite: int = Query(20, ge=1, le=100), busca: str | None = Query(None, max_length=300), tipo_alteracao: str | None = None, db: Session = Depends(get_db), _admin: Usuario = Depends(exigir_admin)):
    rascunho = obter_rascunho(db, rascunho_id)
    if rascunho is None: raise HTTPException(404, "rascunho não encontrado")
    itens, total, paginas = listar_perguntas(db, rascunho, pagina=pagina, limite=limite, busca=busca, tipo_alteracao=tipo_alteracao)
    return PaginaPerguntasRascunho(itens=[_detalhe_pergunta(i) for i in itens], pagina=pagina, limite=limite, total=total, total_paginas=paginas)


@router.get("/catalogos/rascunhos/{rascunho_id}/perguntas/{pergunta_id}", response_model=PerguntaRascunhoDetalhe)
def consultar_pergunta_rascunho_admin(rascunho_id: UUID, pergunta_id: UUID, db: Session = Depends(get_db), _admin: Usuario = Depends(exigir_admin)):
    rascunho = obter_rascunho(db, rascunho_id)
    item = obter_pergunta(db, rascunho, pergunta_id) if rascunho else None
    if item is None: raise HTTPException(404, "pergunta de rascunho não encontrada")
    return _detalhe_pergunta(item)


def _salvar_admin(rascunho_id, pergunta_id, dados, revisao, chave, admin, *, adicionar=False):
    pedido = dados.model_dump(mode="json") | {"revisao": revisao}
    tipo = "ADICIONAR_PERGUNTA_RASCUNHO" if adicionar else "EDITAR_PERGUNTA_RASCUNHO"
    def executar(db):
        usuario = db.get(Usuario, admin.id)
        rascunho = obter_rascunho(db, rascunho_id)
        if rascunho is None:
            raise HTTPException(status_code=404, detail="rascunho não encontrado")
        contrato_compativel = (
            (rascunho.modo == "QUIZ_CLASSICO" and isinstance(dados, PerguntaQuizRascunhoEntrada))
            or (rascunho.modo == "NEM_A_PATO" and isinstance(dados, PerguntaNemPatoRascunhoEntrada))
        )
        if not contrato_compativel:
            raise HTTPException(status_code=422, detail={"codigo": "CONTRATO_MODO_INCOMPATIVEL", "mensagem": "o payload não corresponde ao modo do rascunho"})
        item, nova = (adicionar_pergunta(db, rascunho_id, dados.model_dump(), usuario, revisao) if adicionar else salvar_pergunta(db, rascunho_id, pergunta_id, dados.model_dump(), usuario, revisao))
        return (201 if adicionar else 200), {"id": str(item.id), "revisao_rascunho": nova}
    res = _executar_idempotente(admin=admin, tipo=tipo, recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho_id, chave=chave, pedido=pedido, executar=executar)
    with get_session_factory()() as db:
        rascunho = obter_rascunho(db, rascunho_id); item = obter_pergunta(db, rascunho, UUID(res.resposta["id"]))
        return _detalhe_pergunta(item), res.resposta["revisao_rascunho"]


@router.post("/catalogos/rascunhos/{rascunho_id}/perguntas", response_model=PerguntaRascunhoDetalhe, status_code=201)
def adicionar_pergunta_rascunho_admin(response: Response, rascunho_id: UUID, dados: PerguntaQuizRascunhoEntrada | PerguntaNemPatoRascunhoEntrada, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    item, revisao = _salvar_admin(rascunho_id, None, dados, _revisao_if_match(if_match), chave, admin, adicionar=True); response.headers["ETag"] = f'"{revisao}"'; return item


@router.put("/catalogos/rascunhos/{rascunho_id}/perguntas/{pergunta_id}", response_model=PerguntaRascunhoDetalhe)
def editar_pergunta_rascunho_admin(response: Response, rascunho_id: UUID, pergunta_id: UUID, dados: PerguntaQuizRascunhoEntrada | PerguntaNemPatoRascunhoEntrada, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    item, revisao = _salvar_admin(rascunho_id, pergunta_id, dados, _revisao_if_match(if_match), chave, admin); response.headers["ETag"] = f'"{revisao}"'; return item


def _mudar_estado_pergunta(rascunho_id, pergunta_id, revisao, chave, admin, restaurar):
    tipo = "RESTAURAR_PERGUNTA_RASCUNHO" if restaurar else "REMOVER_PERGUNTA_RASCUNHO"
    def executar(db):
        item, nova = alterar_remocao(db, rascunho_id, pergunta_id, db.get(Usuario, admin.id), revisao, restaurar=restaurar)
        return 200, {"id": str(item.id), "revisao_rascunho": nova}
    return _executar_idempotente(admin=admin, tipo=tipo, recurso_tipo="PERGUNTA_OFICIAL_RASCUNHO", recurso_id=pergunta_id, chave=chave, pedido={"rascunho_id": str(rascunho_id), "revisao": revisao}, executar=executar)


@router.delete("/catalogos/rascunhos/{rascunho_id}/perguntas/{pergunta_id}")
def remover_pergunta_rascunho_admin(rascunho_id: UUID, pergunta_id: UUID, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    return _mudar_estado_pergunta(rascunho_id, pergunta_id, _revisao_if_match(if_match), chave, admin, False).resposta


@router.post("/catalogos/rascunhos/{rascunho_id}/perguntas/{pergunta_id}/restaurar")
def restaurar_pergunta_rascunho_admin(rascunho_id: UUID, pergunta_id: UUID, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    return _mudar_estado_pergunta(rascunho_id, pergunta_id, _revisao_if_match(if_match), chave, admin, True).resposta


@router.get("/catalogos/rascunhos/{rascunho_id}/alteracoes", response_model=PaginaAlteracoesRascunho)
def historico_rascunho_admin(rascunho_id: UUID, pagina: int = Query(1, ge=1), limite: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), _admin: Usuario = Depends(exigir_admin)):
    if obter_rascunho(db, rascunho_id) is None: raise HTTPException(404, "rascunho não encontrado")
    itens, total, paginas = listar_alteracoes(db, rascunho_id, pagina=pagina, limite=limite)
    return PaginaAlteracoesRascunho(itens=[AlteracaoRascunhoPublica.model_validate(i) for i in itens], pagina=pagina, limite=limite, total=total, total_paginas=paginas)


@router.post("/catalogos/rascunhos/{rascunho_id}/descartar", response_model=RascunhoResumo)
def descartar_rascunho_admin(rascunho_id: UUID, dados: DescartarRascunho, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    revisao = _revisao_if_match(if_match)
    def executar(db):
        item = descartar_rascunho(db, rascunho_id, dados.motivo, db.get(Usuario, admin.id), revisao)
        return 200, {"id": str(item.id)}
    res = _executar_idempotente(admin=admin, tipo="DESCARTAR_RASCUNHO_CATALOGO", recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho_id, chave=chave, pedido=dados.model_dump(mode="json") | {"revisao": revisao}, executar=executar)
    with get_session_factory()() as db: return _resumo_rascunho(db, obter_rascunho(db, UUID(res.resposta["id"])))


@router.get("/catalogos/rascunhos/{rascunho_id}/revisao")
def consultar_revisao_editorial(rascunho_id: UUID, db: Session = Depends(get_db), admin: Usuario = Depends(exigir_admin)):
    dados = obter_revisao(db, rascunho_id, admin.id)
    if dados is None: raise HTTPException(404, "rascunho não encontrado")
    return dados


@router.get("/catalogos/rascunhos/{rascunho_id}/revisao/avisos")
def listar_avisos_revisao(
    rascunho_id: UUID,
    pagina: int = Query(1, ge=1),
    limite: int = Query(20, ge=1, le=100),
    estado: Literal["PENDENTE", "ACEITO", "REJEITADO"] | None = None,
    severidade: Literal["ERRO", "AVISO", "INFORMACAO"] | None = None,
    db: Session = Depends(get_db),
    _admin: Usuario = Depends(exigir_admin),
):
    ciclo, registros, total, pendentes = listar_avisos(
        db, rascunho_id, pagina=pagina, limite=limite,
        estado=estado, severidade=severidade,
    )
    return {
        "ciclo_id": ciclo.id,
        "revisao_editorial": ciclo.revisao_editorial,
        "itens": [{
            "id": achado.id, "ciclo_id": achado.ciclo_id,
            "codigo": achado.codigo, "severidade": achado.severidade,
            "pergunta_id": achado.pergunta_id, "id_editorial": achado.id_editorial,
            "campo": achado.campo, "mensagem": achado.mensagem,
            "recomendacao": achado.recomendacao,
            "decisao": decisao.decisao if decisao else None,
            "justificativa": decisao.justificativa if decisao else None,
            "responsavel_id": decisao.responsavel_id if decisao else None,
            "decidida_em": decisao.criada_em if decisao else None,
        } for achado, decisao in registros],
        "pagina": pagina, "limite": limite, "total": total,
        "total_paginas": (total + limite - 1) // limite,
        "total_pendencias": pendentes,
    }


@router.get("/catalogos/rascunhos/{rascunho_id}/revisao/perguntas")
def listar_perguntas_revisao(rascunho_id: UUID, pagina: int = Query(1, ge=1), limite: int = Query(20, ge=1, le=100), estado: Literal["PENDENTE", "APROVADA", "CORRECAO_SOLICITADA", "REPROVADA"] | None = None, db: Session = Depends(get_db), _admin: Usuario = Depends(exigir_admin)):
    ciclo, itens, total = listar_itens(db, rascunho_id, pagina=pagina, limite=limite, estado=estado)
    return {"ciclo_id": ciclo.id, "revisao_editorial": ciclo.revisao_editorial, "itens": [{"id": i.id, "pergunta_id": i.pergunta_quiz_id or i.pergunta_nem_pato_id, "id_editorial": i.id_editorial, "revisao_pergunta": i.revisao_pergunta, "revisao_editorial": i.revisao_editorial, "estado": i.estado, "revisor_id": i.revisor_id} for i in itens], "pagina": pagina, "limite": limite, "total": total}


@router.get("/catalogos/rascunhos/{rascunho_id}/revisao/perguntas/{pergunta_id}/historico")
def historico_revisao_pergunta(rascunho_id: UUID, pergunta_id: UUID, db: Session = Depends(get_db), _admin: Usuario = Depends(exigir_admin)):
    from app.models import CicloRevisaoRascunho, DecisaoRevisaoPergunta, ItemRevisaoPergunta, VerificacaoFonteRevisao
    item = db.scalar(select(ItemRevisaoPergunta).join(CicloRevisaoRascunho).where(CicloRevisaoRascunho.rascunho_id == rascunho_id, ((ItemRevisaoPergunta.pergunta_quiz_id == pergunta_id) | (ItemRevisaoPergunta.pergunta_nem_pato_id == pergunta_id))).order_by(CicloRevisaoRascunho.criado_em.desc()))
    if not item: raise HTTPException(404, "histórico editorial não encontrado")
    decisoes = list(db.scalars(select(DecisaoRevisaoPergunta).where(DecisaoRevisaoPergunta.item_id == item.id).order_by(DecisaoRevisaoPergunta.criada_em)))
    fontes = list(db.scalars(select(VerificacaoFonteRevisao).where(VerificacaoFonteRevisao.item_id == item.id).order_by(VerificacaoFonteRevisao.criada_em)))
    return {"item_id": item.id, "decisoes": [{"id": d.id, "decisao": d.decisao, "justificativa": d.justificativa, "responsavel_id": d.responsavel_id, "revisao_anterior": d.revisao_anterior, "revisao_nova": d.revisao_nova, "criada_em": d.criada_em} for d in decisoes], "verificacoes_fontes": [{"id": f.id, "fonte_titulo": f.fonte_titulo, "fonte_url": f.fonte_url, "resultado": f.resultado, "evidencia_documental": f.evidencia_documental, "relacao_com_resposta": f.relacao_com_resposta, "responsavel_id": f.responsavel_id, "criada_em": f.criada_em} for f in fontes]}


def _op_editorial(admin, chave, tipo, rascunho_id, pedido, executar):
    return _executar_idempotente(admin=admin, tipo=tipo, recurso_tipo="CATALOGO_OFICIAL_RASCUNHO", recurso_id=rascunho_id, chave=chave, pedido=pedido, executar=executar).resposta


@router.post("/catalogos/rascunhos/{rascunho_id}/encaminhar-revisao")
def encaminhar_revisao_admin(rascunho_id: UUID, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    revisao = _revisao_if_match(if_match)
    def executar(db):
        r, c = encaminhar_revisao(db, rascunho_id, revisao, db.get(Usuario, admin.id)); return 201, {"rascunho_id": str(r.id), "ciclo_id": str(c.id), "status": r.status, "revisao_conteudo": r.revisao, "revisao_editorial": c.revisao_editorial}
    return _op_editorial(admin, chave, "ENCAMINHAR_RASCUNHO_REVISAO", rascunho_id, {"revisao": revisao}, executar)


@router.post("/catalogos/rascunhos/{rascunho_id}/revisao/perguntas/{pergunta_id}/decisoes")
def decidir_pergunta_admin(rascunho_id: UUID, pergunta_id: UUID, dados: DecisaoPerguntaEntrada, if_match: str | None = Header(None, alias="If-Match"), revisao_editorial: str | None = Header(None, alias="X-Editorial-Revision"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    rc, re = _revisao_if_match(if_match), _revisao_editorial(revisao_editorial); pedido = dados.model_dump(mode="json") | {"revisao": rc, "revisao_editorial": re, "pergunta_id": str(pergunta_id)}
    def executar(db):
        item, ciclo = decidir_pergunta(db, rascunho_id, pergunta_id, rc, re, dados.model_dump(), db.get(Usuario, admin.id)); return 200, {"item_id": str(item.id), "estado": item.estado, "revisao_editorial_item": item.revisao_editorial, "revisao_editorial": ciclo.revisao_editorial}
    return _op_editorial(admin, chave, "DECIDIR_PERGUNTA_RASCUNHO", rascunho_id, pedido, executar)


@router.post("/catalogos/rascunhos/{rascunho_id}/revisao/perguntas/{pergunta_id}/fontes/{fonte_id}/verificacoes")
def verificar_fonte_admin(rascunho_id: UUID, pergunta_id: UUID, fonte_id: int, dados: VerificacaoFonteEntrada, if_match: str | None = Header(None, alias="If-Match"), revisao_editorial: str | None = Header(None, alias="X-Editorial-Revision"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    rc, re = _revisao_if_match(if_match), _revisao_editorial(revisao_editorial); pedido = dados.model_dump(mode="json") | {"revisao": rc, "revisao_editorial": re, "pergunta_id": str(pergunta_id), "fonte_id": fonte_id}
    def executar(db):
        item, ciclo = verificar_fonte(db, rascunho_id, pergunta_id, fonte_id, rc, re, dados.model_dump(), db.get(Usuario, admin.id)); return 201, {"item_id": str(item.id), "revisao_editorial_item": item.revisao_editorial, "revisao_editorial": ciclo.revisao_editorial}
    return _op_editorial(admin, chave, "VERIFICAR_FONTE_RASCUNHO", rascunho_id, pedido, executar)


@router.post("/catalogos/rascunhos/{rascunho_id}/revisao/avisos/{achado_id}/decisao")
def decidir_aviso_admin(rascunho_id: UUID, achado_id: UUID, dados: DecisaoAvisoEntrada, if_match: str | None = Header(None, alias="If-Match"), revisao_editorial: str | None = Header(None, alias="X-Editorial-Revision"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    rc, re = _revisao_if_match(if_match), _revisao_editorial(revisao_editorial); pedido = dados.model_dump(mode="json") | {"revisao": rc, "revisao_editorial": re, "achado_id": str(achado_id)}
    def executar(db):
        ciclo = decidir_aviso(db, rascunho_id, achado_id, rc, re, dados.model_dump(), db.get(Usuario, admin.id)); return 201, {"ciclo_id": str(ciclo.id), "revisao_editorial": ciclo.revisao_editorial}
    return _op_editorial(admin, chave, "DECIDIR_AVISO_RASCUNHO", rascunho_id, pedido, executar)


def _devolver_admin(rascunho_id, dados, revisao, revisao_editorial, chave, admin, perguntas=None):
    pedido = dados.model_dump(mode="json") | {"revisao": revisao, "revisao_editorial": revisao_editorial}
    def executar(db):
        r, c = devolver_edicao(db, rascunho_id, revisao, dados.justificativa, db.get(Usuario, admin.id), perguntas=perguntas, revisao_editorial=revisao_editorial); return 200, {"rascunho_id": str(r.id), "ciclo_id": str(c.id), "status": r.status, "revisao_conteudo": r.revisao}
    return _op_editorial(admin, chave, "SOLICITAR_CORRECAO_RASCUNHO" if perguntas else "DEVOLVER_RASCUNHO_EDICAO", rascunho_id, pedido, executar)


@router.post("/catalogos/rascunhos/{rascunho_id}/solicitar-correcao")
def solicitar_correcao_admin(rascunho_id: UUID, dados: SolicitarCorrecaoEntrada, if_match: str | None = Header(None, alias="If-Match"), revisao_editorial: str | None = Header(None, alias="X-Editorial-Revision"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    return _devolver_admin(rascunho_id, dados, _revisao_if_match(if_match), _revisao_editorial(revisao_editorial), chave, admin, dados.perguntas)


@router.post("/catalogos/rascunhos/{rascunho_id}/devolver-edicao")
def devolver_edicao_admin(rascunho_id: UUID, dados: MotivoEditorial, if_match: str | None = Header(None, alias="If-Match"), revisao_editorial: str | None = Header(None, alias="X-Editorial-Revision"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    return _devolver_admin(rascunho_id, dados, _revisao_if_match(if_match), _revisao_editorial(revisao_editorial), chave, admin)


@router.post("/catalogos/rascunhos/{rascunho_id}/aprovar")
def aprovar_rascunho_admin(rascunho_id: UUID, dados: AprovarRascunhoEntrada, if_match: str | None = Header(None, alias="If-Match"), revisao_editorial: str | None = Header(None, alias="X-Editorial-Revision"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    rc, re = _revisao_if_match(if_match), _revisao_editorial(revisao_editorial); pedido = dados.model_dump(mode="json") | {"revisao": rc, "revisao_editorial": re}
    def executar(db):
        r, c, a = aprovar(db, rascunho_id, rc, re, dados.model_dump(), db.get(Usuario, admin.id)); return 200, {"rascunho_id": str(r.id), "ciclo_id": str(c.id), "aprovacao_id": str(a.id), "status": r.status, "revisao_conteudo": r.revisao}
    return _op_editorial(admin, chave, "APROVAR_RASCUNHO", rascunho_id, pedido, executar)


@router.post("/catalogos/rascunhos/{rascunho_id}/reabrir")
def reabrir_rascunho_admin(rascunho_id: UUID, dados: MotivoEditorial, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    rc = _revisao_if_match(if_match); pedido = dados.model_dump(mode="json") | {"revisao": rc}
    def executar(db):
        r, c = reabrir(db, rascunho_id, rc, dados.justificativa, db.get(Usuario, admin.id)); return 200, {"rascunho_id": str(r.id), "ciclo_id": str(c.id), "status": r.status, "revisao_conteudo": r.revisao}
    return _op_editorial(admin, chave, "REABRIR_RASCUNHO", rascunho_id, pedido, executar)


@router.post("/catalogos/rascunhos/{rascunho_id}/publicar")
def publicar_rascunho_admin(rascunho_id: UUID, dados: MotivoEditorial, if_match: str | None = Header(None, alias="If-Match"), chave: str | None = Header(None, alias="Idempotency-Key"), admin: Usuario = Depends(exigir_csrf_admin)):
    revisao = _revisao_if_match(if_match)
    pedido = dados.model_dump(mode="json") | {"revisao": revisao}
    def executar(db):
        r, catalogo, total = publicar_rascunho(db, rascunho_id, revisao, db.get(Usuario, admin.id), dados.justificativa)
        return 201, {"rascunho_id": str(r.id), "status": r.status, "catalogo_publicado_id": str(catalogo.id), "catalogo_id": catalogo.catalogo_id, "modo": catalogo.modo, "versao": catalogo.versao, "total_perguntas": total}
    return _op_editorial(admin, chave, "PUBLICAR_RASCUNHO", rascunho_id, pedido, executar)


@router.get("/auditorias", response_model=PaginaAuditoriaAdministrativa)
def listar_auditorias_administrativas(
    pagina: int = Query(default=1, ge=1),
    limite: int = Query(default=20, ge=1, le=100),
    operacao: str | None = Query(default=None, min_length=1, max_length=80),
    administrador_id: UUID | None = None,
    resultado: Literal["SUCESSO", "REJEITADA", "FALHA"] | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    busca: str | None = Query(default=None, min_length=1, max_length=160),
    ordem: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    _administrador: Usuario = Depends(exigir_admin),
):
    if (inicio and inicio.tzinfo is None) or (fim and fim.tzinfo is None):
        raise HTTPException(
            status_code=422,
            detail="as datas devem informar o fuso horário",
        )
    if inicio and fim and inicio > fim:
        raise HTTPException(
            status_code=422,
            detail="a data inicial não pode ser posterior à data final",
        )
    dados = consultar_auditoria_administrativa(
        db,
        pagina=pagina,
        limite=limite,
        operacao=operacao.strip() if operacao else None,
        administrador_id=administrador_id,
        resultado=resultado,
        inicio=inicio,
        fim=fim,
        busca=busca.strip() if busca else None,
        ordem=ordem,
    )
    return PaginaAuditoriaAdministrativa(
        itens=[_serializar_auditoria(item) for item in dados["itens"]],
        pagina=dados["pagina"],
        limite=dados["limite"],
        total=dados["total"],
        total_paginas=dados["total_paginas"],
    )
