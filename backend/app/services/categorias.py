import re
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.conteudo import ORIGEM_OFICIAL
from app.models import Categoria, Usuario


PADRAO_CATEGORIA_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class CategoriaInvalida(ValueError):
    pass


class CategoriaDuplicada(ValueError):
    pass


class CategoriasService:
    @staticmethod
    def listar(
        db: Session, *, somente_ativas: bool = False,
        modo: str = "QUIZ_CLASSICO",
    ) -> list[Categoria]:
        consulta = select(Categoria).where(
            Categoria.modo == modo,
            Categoria.origem == ORIGEM_OFICIAL,
            Categoria.excluida_em.is_(None),
        )
        if somente_ativas:
            consulta = consulta.where(Categoria.ativa.is_(True))
        return list(db.scalars(consulta.order_by(Categoria.nome, Categoria.slug)))

    @staticmethod
    def listar_jogaveis(
        db: Session, usuario: Usuario | None = None
    ) -> list[Categoria]:
        origens_permitidas = Categoria.origem == ORIGEM_OFICIAL
        if usuario is not None:
            origens_permitidas = or_(
                origens_permitidas,
                and_(
                    Categoria.origem == "USUARIO",
                    Categoria.usuario_id == usuario.id,
                ),
            )
        consulta = (
            select(Categoria)
            .where(
                Categoria.modo == "QUIZ_CLASSICO",
                Categoria.ativa.is_(True),
                Categoria.excluida_em.is_(None),
                origens_permitidas,
            )
            .order_by(Categoria.nome, Categoria.slug)
        )
        return list(db.scalars(consulta))

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
        if db.scalar(select(Categoria).where(
            Categoria.slug == codigo,
            Categoria.modo == "QUIZ_CLASSICO",
            Categoria.origem == "OFICIAL",
        )) is not None:
            raise CategoriaDuplicada(f"categoria com id '{codigo}' já existe")

        categoria = Categoria(
            id=uuid4(),
            slug=codigo,
            nome=nome_normalizado,
            descricao=descricao_normalizada,
            modo="QUIZ_CLASSICO",
            origem="OFICIAL",
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
