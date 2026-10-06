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
from app.security import usuario_atual
from app.services.meu_conteudo_categorias import (
    CategoriaNaoEncontrada,
    MeuConteudoErro,
    meu_conteudo_categorias_service,
)


router = APIRouter(prefix="/meu-conteudo", tags=["Meu Conteúdo"])


def _traduzir_erro(erro: MeuConteudoErro) -> HTTPException:
    codigo = (
        status.HTTP_404_NOT_FOUND
        if isinstance(erro, CategoriaNaoEncontrada)
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=codigo, detail=erro.detalhe)


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
