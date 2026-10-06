import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.conteudo import (
    LIMITE_CATEGORIAS_USUARIO_POR_MODO,
    LIMITE_PERGUNTAS_USUARIO_POR_MODO,
    MODO_NEM_A_PATO,
    MODO_QUIZ_CLASSICO,
    MODOS_CONTEUDO,
    ORIGEM_USUARIO,
)
from app.models import Categoria, Pergunta, PerguntaNemPato, Usuario
from app.schemas.meu_conteudo import CategoriaUsuarioCriar, CategoriaUsuarioEditar


class MeuConteudoErro(Exception):
    detalhe = "conflito ao alterar categoria"


class CategoriaNaoEncontrada(MeuConteudoErro):
    detalhe = "categoria não encontrada"


class QuotaCategoriasAtingida(MeuConteudoErro):
    detalhe = "limite de categorias atingido para este modo"


class NomeCategoriaDuplicado(MeuConteudoErro):
    detalhe = "já existe uma categoria com este nome neste modo"


class CategoriaExcluida(MeuConteudoErro):
    detalhe = "categoria excluída não pode ser alterada"


class CategoriaComPerguntas(MeuConteudoErro):
    detalhe = "categoria possui perguntas não excluídas"


def _slug_usuario(nome: str, categoria_id: UUID) -> str:
    base = unicodedata.normalize("NFKD", nome)
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    sufixo = categoria_id.hex[:8]
    if not base:
        base = "categoria"
    return f"{base[:71].rstrip('-')}-{sufixo}"


def _filtros_proprietario(usuario_id: UUID):
    return (
        Categoria.origem == ORIGEM_USUARIO,
        Categoria.usuario_id == usuario_id,
    )


def _categoria_propria(
    db: Session, usuario_id: UUID, categoria_id: UUID, *, bloquear: bool = False
) -> Categoria:
    consulta = select(Categoria).where(
        Categoria.id == categoria_id,
        *_filtros_proprietario(usuario_id),
    )
    if bloquear:
        consulta = consulta.with_for_update()
    categoria = db.scalar(consulta)
    if categoria is None:
        raise CategoriaNaoEncontrada
    return categoria


def _bloquear_usuario(db: Session, usuario_id: UUID) -> None:
    usuario = db.scalar(
        select(Usuario).where(Usuario.id == usuario_id).with_for_update()
    )
    if usuario is None:
        raise CategoriaNaoEncontrada


def _nome_duplicado(erro: IntegrityError) -> bool:
    diagnostico = getattr(erro.orig, "diag", None)
    nome_constraint = getattr(diagnostico, "constraint_name", None)
    return nome_constraint == "uq_categorias_usuario_modo_nome" or (
        "uq_categorias_usuario_modo_nome" in str(erro.orig)
        or "categorias.usuario_id, categorias.modo" in str(erro.orig)
    )


class MeuConteudoCategoriasService:
    def resumo(self, db: Session, usuario_id: UUID) -> dict:
        modos = []
        modelo_perguntas = {
            MODO_QUIZ_CLASSICO: Pergunta,
            MODO_NEM_A_PATO: PerguntaNemPato,
        }
        for modo in MODOS_CONTEUDO:
            categorias = db.scalar(
                select(func.count(Categoria.id)).where(
                    *_filtros_proprietario(usuario_id),
                    Categoria.modo == modo,
                    Categoria.excluida_em.is_(None),
                )
            )
            pergunta = modelo_perguntas[modo]
            perguntas = db.scalar(
                select(func.count(pergunta.id))
                .join(Categoria, Categoria.id == pergunta.categoria_id)
                .where(
                    pergunta.origem == ORIGEM_USUARIO,
                    pergunta.usuario_id == usuario_id,
                    pergunta.excluida_em.is_(None),
                    Categoria.modo == modo,
                )
            )
            modos.append(
                {
                    "modo": modo,
                    "categorias": {
                        "usadas": categorias or 0,
                        "limite": LIMITE_CATEGORIAS_USUARIO_POR_MODO,
                    },
                    "perguntas": {
                        "usadas": perguntas or 0,
                        "limite": LIMITE_PERGUNTAS_USUARIO_POR_MODO,
                    },
                }
            )
        return {"modos": modos}

    def listar(
        self,
        db: Session,
        usuario_id: UUID,
        *,
        modo: str | None,
        ativa: bool | None,
        incluir_excluidas: bool,
    ) -> list[Categoria]:
        consulta = select(Categoria).where(*_filtros_proprietario(usuario_id))
        if modo is not None:
            consulta = consulta.where(Categoria.modo == modo)
        if ativa is not None:
            consulta = consulta.where(Categoria.ativa.is_(ativa))
        if not incluir_excluidas:
            consulta = consulta.where(Categoria.excluida_em.is_(None))
        consulta = consulta.order_by(
            Categoria.modo, func.lower(func.trim(Categoria.nome)), Categoria.id
        )
        return list(db.scalars(consulta))

    def obter(self, db: Session, usuario_id: UUID, categoria_id: UUID) -> Categoria:
        return _categoria_propria(db, usuario_id, categoria_id)

    def criar(
        self, db: Session, usuario_id: UUID, dados: CategoriaUsuarioCriar
    ) -> Categoria:
        try:
            _bloquear_usuario(db, usuario_id)
            total = db.scalar(
                select(func.count(Categoria.id)).where(
                    *_filtros_proprietario(usuario_id),
                    Categoria.modo == dados.modo,
                    Categoria.excluida_em.is_(None),
                )
            )
            if (total or 0) >= LIMITE_CATEGORIAS_USUARIO_POR_MODO:
                raise QuotaCategoriasAtingida

            categoria_id = uuid4()
            categoria = Categoria(
                id=categoria_id,
                slug=_slug_usuario(dados.nome, categoria_id),
                nome=dados.nome,
                descricao=dados.descricao,
                modo=dados.modo,
                origem=ORIGEM_USUARIO,
                usuario_id=usuario_id,
                ativa=True,
            )
            db.add(categoria)
            db.flush()
            db.commit()
            db.refresh(categoria)
            return categoria
        except IntegrityError as erro:
            db.rollback()
            if _nome_duplicado(erro):
                raise NomeCategoriaDuplicado from None
            raise
        except Exception:
            db.rollback()
            raise

    def editar(
        self,
        db: Session,
        usuario_id: UUID,
        categoria_id: UUID,
        dados: CategoriaUsuarioEditar,
    ) -> Categoria:
        try:
            _bloquear_usuario(db, usuario_id)
            categoria = _categoria_propria(
                db, usuario_id, categoria_id, bloquear=True
            )
            if categoria.excluida_em is not None:
                raise CategoriaExcluida
            alteracoes = dados.model_dump(exclude_unset=True)
            for campo, valor in alteracoes.items():
                setattr(categoria, campo, valor)
            categoria.atualizada_em = datetime.now(timezone.utc)
            db.flush()
            db.commit()
            db.refresh(categoria)
            return categoria
        except IntegrityError as erro:
            db.rollback()
            if _nome_duplicado(erro):
                raise NomeCategoriaDuplicado from None
            raise
        except Exception:
            db.rollback()
            raise

    def excluir(
        self, db: Session, usuario_id: UUID, categoria_id: UUID
    ) -> None:
        try:
            _bloquear_usuario(db, usuario_id)
            categoria = _categoria_propria(
                db, usuario_id, categoria_id, bloquear=True
            )
            if categoria.excluida_em is not None:
                raise CategoriaExcluida
            modelo = (
                Pergunta
                if categoria.modo == MODO_QUIZ_CLASSICO
                else PerguntaNemPato
            )
            pergunta = db.scalar(
                select(modelo.id).where(
                    modelo.categoria_id == categoria.id,
                    modelo.excluida_em.is_(None),
                ).limit(1)
            )
            if pergunta is not None:
                raise CategoriaComPerguntas
            agora = datetime.now(timezone.utc)
            categoria.ativa = False
            categoria.excluida_em = agora
            categoria.atualizada_em = agora
            db.flush()
            db.commit()
        except Exception:
            db.rollback()
            raise


meu_conteudo_categorias_service = MeuConteudoCategoriasService()
