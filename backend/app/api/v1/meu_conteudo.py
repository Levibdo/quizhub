from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.schemas.meu_conteudo import (
    CategoriaUsuarioCriar,
    CategoriaUsuarioEditar,
    CategoriaUsuarioResposta,
    ModoConteudo,
    ResumoMeuConteudo,
)
from app.schemas.meu_conteudo_perguntas import (
    PerguntaClassicaCriar,
    PerguntaClassicaEditar,
    PerguntaClassicaResposta,
    PerguntaNemPatoCriar,
    PerguntaNemPatoEditar,
    PerguntaNemPatoResposta,
)
from app.security import usuario_atual
from app.services.meu_conteudo_categorias import (
    CategoriaNaoEncontrada,
    MeuConteudoErro,
    meu_conteudo_categorias_service,
)
from app.services.meu_conteudo_perguntas import (
    CategoriaPerguntaNaoEncontrada,
    MeuConteudoPerguntasErro,
    PerguntaNaoEncontrada,
    meu_conteudo_perguntas_service,
)
from app.models import Pergunta, PerguntaNemPato


router = APIRouter(prefix="/meu-conteudo", tags=["Meu Conteúdo"])


def _traduzir_erro(erro: MeuConteudoErro) -> HTTPException:
    codigo = (
        status.HTTP_404_NOT_FOUND
        if isinstance(erro, CategoriaNaoEncontrada)
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=codigo, detail=erro.detalhe)


def _traduzir_erro_pergunta(erro: MeuConteudoPerguntasErro) -> HTTPException:
    nao_encontrado = isinstance(
        erro, (PerguntaNaoEncontrada, CategoriaPerguntaNaoEncontrada)
    )
    return HTTPException(
        status_code=(
            status.HTTP_404_NOT_FOUND if nao_encontrado else status.HTTP_409_CONFLICT
        ),
        detail=erro.detalhe,
    )


@router.get("/resumo", response_model=ResumoMeuConteudo)
def obter_resumo(
    db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)
):
    return meu_conteudo_categorias_service.resumo(db, usuario.id)


@router.get("/categorias", response_model=list[CategoriaUsuarioResposta])
def listar_categorias(
    modo: ModoConteudo | None = None,
    ativa: bool | None = None,
    include_deleted: Annotated[bool, Query()] = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    return meu_conteudo_categorias_service.listar(
        db,
        usuario.id,
        modo=modo,
        ativa=ativa,
        incluir_excluidas=include_deleted,
    )


@router.post(
    "/categorias",
    response_model=CategoriaUsuarioResposta,
    status_code=status.HTTP_201_CREATED,
)
def criar_categoria(
    dados: CategoriaUsuarioCriar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        return meu_conteudo_categorias_service.criar(db, usuario.id, dados)
    except MeuConteudoErro as erro:
        raise _traduzir_erro(erro) from None


@router.get("/categorias/{categoria_id}", response_model=CategoriaUsuarioResposta)
def obter_categoria(
    categoria_id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        return meu_conteudo_categorias_service.obter(db, usuario.id, categoria_id)
    except MeuConteudoErro as erro:
        raise _traduzir_erro(erro) from None


@router.patch("/categorias/{categoria_id}", response_model=CategoriaUsuarioResposta)
def editar_categoria(
    categoria_id: UUID,
    dados: CategoriaUsuarioEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        return meu_conteudo_categorias_service.editar(
            db, usuario.id, categoria_id, dados
        )
    except MeuConteudoErro as erro:
        raise _traduzir_erro(erro) from None


@router.delete(
    "/categorias/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT
)
def excluir_categoria(
    categoria_id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        meu_conteudo_categorias_service.excluir(db, usuario.id, categoria_id)
    except MeuConteudoErro as erro:
        raise _traduzir_erro(erro) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/perguntas/classico", response_model=list[PerguntaClassicaResposta]
)
def listar_perguntas_classicas(
    categoria_id: UUID | None = None,
    ativa: bool | None = None,
    include_deleted: Annotated[bool, Query()] = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        perguntas = meu_conteudo_perguntas_service.listar(
            db, Pergunta, usuario.id, "QUIZ_CLASSICO",
            categoria_id=categoria_id, ativa=ativa,
            incluir_excluidas=include_deleted, offset=offset, limite=limit,
        )
        return [
            meu_conteudo_perguntas_service.resposta_classica(item)
            for item in perguntas
        ]
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.post(
    "/perguntas/classico",
    response_model=PerguntaClassicaResposta,
    status_code=status.HTTP_201_CREATED,
)
def criar_pergunta_classica(
    dados: PerguntaClassicaCriar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        pergunta = meu_conteudo_perguntas_service.criar_classica(
            db, usuario.id, dados
        )
        return meu_conteudo_perguntas_service.resposta_classica(pergunta)
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.get(
    "/perguntas/classico/{pergunta_id}", response_model=PerguntaClassicaResposta
)
def obter_pergunta_classica(
    pergunta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        pergunta = meu_conteudo_perguntas_service.obter(
            db, Pergunta, usuario.id, pergunta_id
        )
        return meu_conteudo_perguntas_service.resposta_classica(pergunta)
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.patch(
    "/perguntas/classico/{pergunta_id}", response_model=PerguntaClassicaResposta
)
def editar_pergunta_classica(
    pergunta_id: int,
    dados: PerguntaClassicaEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        pergunta = meu_conteudo_perguntas_service.editar_classica(
            db, usuario.id, pergunta_id, dados
        )
        return meu_conteudo_perguntas_service.resposta_classica(pergunta)
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.delete(
    "/perguntas/classico/{pergunta_id}", status_code=status.HTTP_204_NO_CONTENT
)
def excluir_pergunta_classica(
    pergunta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        meu_conteudo_perguntas_service.excluir(
            db, Pergunta, usuario.id, pergunta_id
        )
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/perguntas/nem-a-pato", response_model=list[PerguntaNemPatoResposta]
)
def listar_perguntas_nem_pato(
    categoria_id: UUID | None = None,
    ativa: bool | None = None,
    include_deleted: Annotated[bool, Query()] = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        return meu_conteudo_perguntas_service.listar(
            db, PerguntaNemPato, usuario.id, "NEM_A_PATO",
            categoria_id=categoria_id, ativa=ativa,
            incluir_excluidas=include_deleted, offset=offset, limite=limit,
        )
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.post(
    "/perguntas/nem-a-pato",
    response_model=PerguntaNemPatoResposta,
    status_code=status.HTTP_201_CREATED,
)
def criar_pergunta_nem_pato(
    dados: PerguntaNemPatoCriar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        return meu_conteudo_perguntas_service.criar_nem_pato(
            db, usuario.id, dados
        )
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.get(
    "/perguntas/nem-a-pato/{pergunta_id}", response_model=PerguntaNemPatoResposta
)
def obter_pergunta_nem_pato(
    pergunta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        return meu_conteudo_perguntas_service.obter(
            db, PerguntaNemPato, usuario.id, pergunta_id
        )
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.patch(
    "/perguntas/nem-a-pato/{pergunta_id}", response_model=PerguntaNemPatoResposta
)
def editar_pergunta_nem_pato(
    pergunta_id: int,
    dados: PerguntaNemPatoEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        return meu_conteudo_perguntas_service.editar_nem_pato(
            db, usuario.id, pergunta_id, dados
        )
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None


@router.delete(
    "/perguntas/nem-a-pato/{pergunta_id}", status_code=status.HTTP_204_NO_CONTENT
)
def excluir_pergunta_nem_pato(
    pergunta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        meu_conteudo_perguntas_service.excluir(
            db, PerguntaNemPato, usuario.id, pergunta_id
        )
    except MeuConteudoPerguntasErro as erro:
        raise _traduzir_erro_pergunta(erro) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
