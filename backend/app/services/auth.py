from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Usuario
from app.security import DUMMY_HASH, password_hash

ERRO_CREDENCIAIS = "e-mail ou senha inválidos"


class Autenticacao:
    def cadastrar(self, db: Session, nome: str, email: str, senha: str) -> Usuario:
        email = email.strip().lower()
        if db.scalar(select(Usuario.id).where(Usuario.email == email)) is not None:
            raise HTTPException(status_code=409, detail="e-mail já cadastrado")

        usuario = Usuario(
            nome=nome,
            email=email,
            senha_hash=password_hash.hash(senha),
        )
        db.add(usuario)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(status_code=409, detail="e-mail já cadastrado") from error
        return usuario

    def autenticar(self, db: Session, email: str, senha: str) -> Usuario:
        email = email.strip().lower()
        usuario = db.scalar(select(Usuario).where(Usuario.email == email))
        hash_verificado = usuario.senha_hash if usuario is not None else DUMMY_HASH
        senha_valida = password_hash.verify(senha, hash_verificado)

        if usuario is None or not senha_valida or not usuario.ativo:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERRO_CREDENCIAIS,
            )
        return usuario


autenticacao = Autenticacao()
