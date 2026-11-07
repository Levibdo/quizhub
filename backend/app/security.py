import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario

JWT_SECRET_ENV = "JWT_SECRET"
JWT_COOKIE_SECURE_ENV = "JWT_COOKIE_SECURE"
JWT_ALGORITHM = "HS256"
JWT_COOKIE_NAME = "quizhub_access_token"
CSRF_COOKIE_NAME = "quizhub_csrf_token"
CLASSIC_GUEST_COOKIE_NAME = "quizhub_classic_guest"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_TRUSTED_ORIGINS_ENV = "CSRF_TRUSTED_ORIGINS"
SESSAO_DURACAO = timedelta(hours=8)
CSRF_DURACAO = timedelta(minutes=30)
CLASSIC_GUEST_DURATION = timedelta(days=30)

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


def criar_token_visitante_classico(
    visitante_id: UUID,
    agora: datetime | None = None,
    duracao: timedelta = CLASSIC_GUEST_DURATION,
) -> str:
    emitido_em = agora or datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(visitante_id),
            "iat": emitido_em,
            "exp": emitido_em + duracao,
            "tipo": "visitante_classico",
        },
        obter_segredo_jwt(),
        algorithm=JWT_ALGORITHM,
    )


def identificar_visitante_classico(token: str | None) -> UUID | None:
    if token is None:
        return None
    try:
        payload = jwt.decode(
            token,
            obter_segredo_jwt(),
            algorithms=[JWT_ALGORITHM],
        )
        if payload.get("tipo") != "visitante_classico":
            return None
        return UUID(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def _identificador_sessao(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_token_csrf(
    usuario_id: UUID,
    token_sessao: str,
    agora: datetime | None = None,
    duracao: timedelta = CSRF_DURACAO,
) -> str:
    emitido_em = agora or datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(usuario_id),
            "sid": _identificador_sessao(token_sessao),
            "iat": emitido_em,
            "exp": emitido_em + duracao,
            "tipo": "csrf",
        },
        obter_segredo_jwt(),
        algorithm=JWT_ALGORITHM,
    )


def _erro_csrf(codigo: str, mensagem: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"codigo": codigo, "mensagem": mensagem},
    )


def _origem_http(valor: str) -> str | None:
    try:
        partes = urlsplit(valor)
    except ValueError:
        return None
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        return None
    return f"{partes.scheme}://{partes.netloc}".lower()


def _origens_csrf_permitidas(request: Request) -> set[str]:
    configuradas = {
        origem
        for item in (
            os.getenv(CSRF_TRUSTED_ORIGINS_ENV, ""),
            os.getenv("CORS_ORIGINS", ""),
        )
        for valor in item.split(",")
        if (origem := _origem_http(valor.strip())) is not None
    }
    origem_requisicao = _origem_http(str(request.base_url))
    if origem_requisicao is not None:
        configuradas.add(origem_requisicao)
    return configuradas


def validar_origem_csrf(request: Request) -> None:
    origem = request.headers.get("origin")
    if origem is None:
        origem = request.headers.get("referer")
    normalizada = _origem_http(origem) if origem else None
    if normalizada is None:
        raise _erro_csrf("CSRF_ORIGEM_AUSENTE", "origem da requisição ausente")
    if normalizada not in _origens_csrf_permitidas(request):
        raise _erro_csrf(
            "CSRF_ORIGEM_INVALIDA", "origem da requisição não autorizada"
        )


def exigir_origem_confiavel(request: Request) -> None:
    """Protege escritas por cookie quando não existe token CSRF de usuário."""
    validar_origem_csrf(request)


def validar_token_csrf(
    token_csrf: str,
    token_sessao: str,
    usuario: Usuario,
) -> None:
    try:
        payload = jwt.decode(
            token_csrf,
            obter_segredo_jwt(),
            algorithms=[JWT_ALGORITHM],
        )
        if payload.get("tipo") != "csrf":
            raise ValueError
        if not hmac.compare_digest(payload.get("sub", ""), str(usuario.id)):
            raise ValueError
        if not hmac.compare_digest(
            payload.get("sid", ""), _identificador_sessao(token_sessao)
        ):
            raise ValueError
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise _erro_csrf("CSRF_TOKEN_INVALIDO", "token CSRF inválido") from None


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


def exigir_admin(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    if usuario.perfil != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="acesso exclusivo para administradores",
        )
    return usuario


def exigir_csrf_admin(
    request: Request,
    usuario: Usuario = Depends(exigir_admin),
    token_sessao: str | None = Cookie(default=None, alias=JWT_COOKIE_NAME),
    token_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE_NAME),
    token_header: str | None = Header(default=None, alias=CSRF_HEADER_NAME),
) -> Usuario:
    if token_sessao is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="não autenticado",
        )
    if token_cookie is None or token_header is None:
        raise _erro_csrf("CSRF_TOKEN_AUSENTE", "token CSRF ausente")
    if not hmac.compare_digest(token_cookie, token_header):
        raise _erro_csrf("CSRF_TOKEN_DIVERGENTE", "token CSRF divergente")
    validar_origem_csrf(request)
    validar_token_csrf(token_header, token_sessao, usuario)
    return usuario
