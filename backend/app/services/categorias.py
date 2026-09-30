import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Categoria


PADRAO_CATEGORIA_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class CategoriaInvalida(ValueError):
    pass


class CategoriaDuplicada(ValueError):
    pass


class CategoriasService:
    @staticmethod
    def listar(db: Session, *, somente_ativas: bool = False) -> list[Categoria]:
        consulta = select(Categoria)
        if somente_ativas:
            consulta = consulta.where(Categoria.ativa.is_(True))
        return list(db.scalars(consulta.order_by(Categoria.nome, Categoria.id)))

    @staticmethod
    def criar(
        db: Session,
        categoria_id: str,
        nome: str,
        descricao: str | None = None,
    ) -> Categoria:
        codigo = categoria_id.strip() if isinstance(categoria_id, str) else ""
        nome_normalizado = nome.strip() if isinstance(nome, str) else ""
        descricao_normalizada = (
            descricao.strip() if isinstance(descricao, str) else None
        ) or None

        if not codigo:
            raise CategoriaInvalida("código/id é obrigatório")
        if len(codigo) > 50 or not PADRAO_CATEGORIA_ID.fullmatch(codigo):
            raise CategoriaInvalida(
                "código/id deve começar com letra minúscula e conter somente "
                "letras minúsculas, números e hífens (máximo de 50 caracteres)"
            )
        if not nome_normalizado:
            raise CategoriaInvalida("nome é obrigatório")
        if db.get(Categoria, codigo) is not None:
            raise CategoriaDuplicada(f"categoria com id '{codigo}' já existe")

        categoria = Categoria(
            id=codigo,
            nome=nome_normalizado,
            descricao=descricao_normalizada,
            ativa=True,
        )
        try:
            db.add(categoria)
            db.commit()
            db.refresh(categoria)
            return categoria
        except IntegrityError as erro:
            db.rollback()
            raise CategoriaDuplicada(
                f"categoria com id '{codigo}' já existe"
            ) from erro


categorias_service = CategoriasService()
