from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.schemas.auth import CadastroUsuario, LoginUsuario, UsuarioPublico
from app.security import (
    JWT_COOKIE_NAME,
    SESSAO_DURACAO,
    cookie_secure,
    criar_token_acesso,
    usuario_atual,
)
from app.services.auth import autenticacao

router = APIRouter(prefix="/auth", tags=["auth"])


def _definir_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=JWT_COOKIE_NAME,
        value=token,
        max_age=int(SESSAO_DURACAO.total_seconds()),
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


@router.post("/cadastro", response_model=UsuarioPublico, status_code=201)
def cadastrar(
    entrada: CadastroUsuario,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        usuario = autenticacao.cadastrar(
            db, entrada.nome, entrada.email, entrada.senha
        )
        token = criar_token_acesso(usuario.id)
        db.commit()
        db.refresh(usuario)
    except Exception:
        db.rollback()
        raise
    _definir_cookie(response, token)
    return usuario


@router.post("/login", response_model=UsuarioPublico)
def login(
    entrada: LoginUsuario,
    response: Response,
    db: Session = Depends(get_db),
):
    usuario = autenticacao.autenticar(db, entrada.email, entrada.senha)
    _definir_cookie(response, criar_token_acesso(usuario.id))
    return usuario


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(
        key=JWT_COOKIE_NAME,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


@router.get("/me", response_model=UsuarioPublico)
def me(usuario: Usuario = Depends(usuario_atual)):
    return usuario
