import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario

JWT_SECRET_ENV = "JWT_SECRET"
JWT_COOKIE_SECURE_ENV = "JWT_COOKIE_SECURE"
JWT_ALGORITHM = "HS256"
JWT_COOKIE_NAME = "quizhub_access_token"
SESSAO_DURACAO = timedelta(hours=8)

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("quizhub-dummy-password")


def obter_segredo_jwt() -> str:
    segredo = os.getenv(JWT_SECRET_ENV, "").strip()
    if not segredo:
        raise RuntimeError(f"{JWT_SECRET_ENV} não está configurado")
    return segredo


def cookie_secure() -> bool:
    return os.getenv(JWT_COOKIE_SECURE_ENV, "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def criar_token_acesso(
    usuario_id: UUID,
    agora: datetime | None = None,
    duracao: timedelta = SESSAO_DURACAO,
) -> str:
    emitido_em = agora or datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(usuario_id),
            "iat": emitido_em,
            "exp": emitido_em + duracao,
            "tipo": "acesso",
        },
        obter_segredo_jwt(),
        algorithm=JWT_ALGORITHM,
    )


def identificar_usuario(token: str, db: Session) -> Usuario:
    erro = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="não autenticado",
    )
    try:
        payload = jwt.decode(
            token,
            obter_segredo_jwt(),
            algorithms=[JWT_ALGORITHM],
        )
        if payload.get("tipo") != "acesso":
            raise erro
        usuario_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise erro from None

    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise erro
    return usuario


def usuario_atual_opcional(
    token: str | None = Cookie(default=None, alias=JWT_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Usuario | None:
    if token is None:
        return None
    return identificar_usuario(token, db)


def usuario_atual(
    usuario: Usuario | None = Depends(usuario_atual_opcional),
) -> Usuario:
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="não autenticado",
        )
    return usuario
