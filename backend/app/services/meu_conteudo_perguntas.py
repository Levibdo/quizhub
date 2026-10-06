from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.conteudo import (
    LIMITE_PERGUNTAS_USUARIO_POR_MODO,
    MODO_NEM_A_PATO,
    MODO_QUIZ_CLASSICO,
    ORIGEM_USUARIO,
)
from app.models import Categoria, Pergunta, PerguntaNemPato, Usuario
from app.schemas.meu_conteudo_perguntas import (
    PerguntaClassicaCriar,
    PerguntaClassicaEditar,
    PerguntaNemPatoCriar,
    PerguntaNemPatoEditar,
)


ALTERNATIVA_PARA_INDICE = {"A": 0, "B": 1, "C": 2, "D": 3}
INDICE_PARA_ALTERNATIVA = {indice: letra for letra, indice in ALTERNATIVA_PARA_INDICE.items()}


class MeuConteudoPerguntasErro(Exception):
    detalhe = "conflito ao alterar pergunta"


class PerguntaNaoEncontrada(MeuConteudoPerguntasErro):
    detalhe = "pergunta não encontrada"


class CategoriaPerguntaNaoEncontrada(MeuConteudoPerguntasErro):
    detalhe = "categoria não encontrada"


class CategoriaPerguntaIndisponivel(MeuConteudoPerguntasErro):
    detalhe = "categoria precisa estar ativa e não excluída"


class PerguntaExcluida(MeuConteudoPerguntasErro):
    detalhe = "pergunta excluída não pode ser alterada"


class QuotaPerguntasAtingida(MeuConteudoPerguntasErro):
    detalhe = "limite de perguntas atingido para este modo"


def _bloquear_usuario(db: Session, usuario_id: UUID) -> None:
    usuario = db.scalar(
        select(Usuario).where(Usuario.id == usuario_id).with_for_update()
    )
    if usuario is None:
        raise PerguntaNaoEncontrada


def _categoria_propria(
    db: Session,
    usuario_id: UUID,
    categoria_id: UUID,
    modo: str,
    *,
    bloquear: bool = False,
    exigir_ativa: bool = False,
) -> Categoria:
    consulta = select(Categoria).where(
        Categoria.id == categoria_id,
        Categoria.origem == ORIGEM_USUARIO,
        Categoria.usuario_id == usuario_id,
        Categoria.modo == modo,
    )
    if bloquear:
        consulta = consulta.with_for_update()
    categoria = db.scalar(consulta)
    if categoria is None:
        raise CategoriaPerguntaNaoEncontrada
    if exigir_ativa and (not categoria.ativa or categoria.excluida_em is not None):
        raise CategoriaPerguntaIndisponivel
    return categoria


def _pergunta_propria(
    db: Session, modelo, usuario_id: UUID, pergunta_id: int, *, bloquear: bool = False
):
    consulta = select(modelo).where(
        modelo.id == pergunta_id,
        modelo.origem == ORIGEM_USUARIO,
        modelo.usuario_id == usuario_id,
    )
    if bloquear:
        consulta = consulta.with_for_update()
    pergunta = db.scalar(consulta)
    if pergunta is None:
        raise PerguntaNaoEncontrada
    return pergunta


def _proximo_id_classico(db: Session) -> int:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("LOCK TABLE perguntas IN SHARE ROW EXCLUSIVE MODE"))
    return (db.scalar(select(func.max(Pergunta.id))) or 0) + 1


def _resposta_classica(pergunta: Pergunta) -> dict:
    return {
        "id": pergunta.id,
        "categoria_id": pergunta.categoria_id,
        "enunciado": pergunta.enunciado,
        "alternativa_a": pergunta.alternativa_a,
        "alternativa_b": pergunta.alternativa_b,
        "alternativa_c": pergunta.alternativa_c,
        "alternativa_d": pergunta.alternativa_d,
        "alternativa_correta": INDICE_PARA_ALTERNATIVA[pergunta.alternativa_correta],
        "explicacao": pergunta.explicacao,
        "ativa": pergunta.ativa,
        "criada_em": pergunta.criada_em,
        "atualizada_em": pergunta.atualizada_em,
        "excluida_em": pergunta.excluida_em,
    }


class MeuConteudoPerguntasService:
    def listar(
        self,
        db: Session,
        modelo,
        usuario_id: UUID,
        modo: str,
        *,
        categoria_id: UUID | None,
        ativa: bool | None,
        incluir_excluidas: bool,
        offset: int,
        limite: int,
    ) -> list:
        if categoria_id is not None:
            _categoria_propria(db, usuario_id, categoria_id, modo)
        consulta = select(modelo).where(
            modelo.origem == ORIGEM_USUARIO,
            modelo.usuario_id == usuario_id,
        )
        if categoria_id is not None:
            consulta = consulta.where(modelo.categoria_id == categoria_id)
        if ativa is not None:
            consulta = consulta.where(modelo.ativa.is_(ativa))
        if not incluir_excluidas:
            consulta = consulta.where(modelo.excluida_em.is_(None))
        return list(db.scalars(consulta.order_by(modelo.id).offset(offset).limit(limite)))

    def obter(self, db: Session, modelo, usuario_id: UUID, pergunta_id: int):
        return _pergunta_propria(db, modelo, usuario_id, pergunta_id)

    def criar_classica(
        self, db: Session, usuario_id: UUID, dados: PerguntaClassicaCriar
    ) -> Pergunta:
        try:
            _bloquear_usuario(db, usuario_id)
            _categoria_propria(
                db, usuario_id, dados.categoria_id, MODO_QUIZ_CLASSICO,
                bloquear=True, exigir_ativa=True,
            )
            total = db.scalar(select(func.count(Pergunta.id)).where(
                Pergunta.origem == ORIGEM_USUARIO,
                Pergunta.usuario_id == usuario_id,
                Pergunta.excluida_em.is_(None),
            ))
            if (total or 0) >= LIMITE_PERGUNTAS_USUARIO_POR_MODO:
                raise QuotaPerguntasAtingida
            pergunta = Pergunta(
                id=_proximo_id_classico(db),
                categoria_id=dados.categoria_id,
                enunciado=dados.enunciado,
                alternativa_a=dados.alternativa_a,
                alternativa_b=dados.alternativa_b,
                alternativa_c=dados.alternativa_c,
                alternativa_d=dados.alternativa_d,
                alternativa_correta=ALTERNATIVA_PARA_INDICE[dados.alternativa_correta],
                explicacao=dados.explicacao,
                origem=ORIGEM_USUARIO,
                usuario_id=usuario_id,
                ativa=True,
            )
            db.add(pergunta)
            db.flush()
            db.commit()
            db.refresh(pergunta)
            return pergunta
        except Exception:
            db.rollback()
            raise

    def criar_nem_pato(
        self, db: Session, usuario_id: UUID, dados: PerguntaNemPatoCriar
    ) -> PerguntaNemPato:
        try:
            _bloquear_usuario(db, usuario_id)
            _categoria_propria(
                db, usuario_id, dados.categoria_id, MODO_NEM_A_PATO,
                bloquear=True, exigir_ativa=True,
            )
            total = db.scalar(select(func.count(PerguntaNemPato.id)).where(
                PerguntaNemPato.origem == ORIGEM_USUARIO,
                PerguntaNemPato.usuario_id == usuario_id,
                PerguntaNemPato.excluida_em.is_(None),
            ))
            if (total or 0) >= LIMITE_PERGUNTAS_USUARIO_POR_MODO:
                raise QuotaPerguntasAtingida
            pergunta = PerguntaNemPato(
                **dados.model_dump(), origem=ORIGEM_USUARIO,
                usuario_id=usuario_id, ativa=True,
            )
            db.add(pergunta)
            db.flush()
            db.commit()
            db.refresh(pergunta)
            return pergunta
        except Exception:
            db.rollback()
            raise

    def editar_classica(
        self, db: Session, usuario_id: UUID, pergunta_id: int,
        dados: PerguntaClassicaEditar,
    ) -> Pergunta:
        return self._editar(
            db, Pergunta, usuario_id, pergunta_id, dados,
            MODO_QUIZ_CLASSICO, classica=True,
        )

    def editar_nem_pato(
        self, db: Session, usuario_id: UUID, pergunta_id: int,
        dados: PerguntaNemPatoEditar,
    ) -> PerguntaNemPato:
        return self._editar(
            db, PerguntaNemPato, usuario_id, pergunta_id, dados,
            MODO_NEM_A_PATO, classica=False,
        )

    def _editar(
        self, db, modelo, usuario_id, pergunta_id, dados, modo, *, classica
    ):
        try:
            _bloquear_usuario(db, usuario_id)
            pergunta = _pergunta_propria(
                db, modelo, usuario_id, pergunta_id, bloquear=True
            )
            if pergunta.excluida_em is not None:
                raise PerguntaExcluida
            alteracoes = dados.model_dump(exclude_unset=True)
            categoria_alvo = alteracoes.get("categoria_id", pergunta.categoria_id)
            movendo = categoria_alvo != pergunta.categoria_id
            reativando = not pergunta.ativa and alteracoes.get("ativa") is True
            if movendo or reativando:
                _categoria_propria(
                    db, usuario_id, categoria_alvo, modo,
                    bloquear=True, exigir_ativa=True,
                )
            if classica and "alternativa_correta" in alteracoes:
                alteracoes["alternativa_correta"] = ALTERNATIVA_PARA_INDICE[
                    alteracoes["alternativa_correta"]
                ]
            for campo, valor in alteracoes.items():
                setattr(pergunta, campo, valor)
            pergunta.atualizada_em = datetime.now(timezone.utc)
            db.flush()
            db.commit()
            db.refresh(pergunta)
            return pergunta
        except Exception:
            db.rollback()
            raise

    def excluir(self, db: Session, modelo, usuario_id: UUID, pergunta_id: int) -> None:
        try:
            _bloquear_usuario(db, usuario_id)
            pergunta = _pergunta_propria(
                db, modelo, usuario_id, pergunta_id, bloquear=True
            )
            if pergunta.excluida_em is not None:
                raise PerguntaExcluida
            agora = datetime.now(timezone.utc)
            pergunta.ativa = False
            pergunta.excluida_em = agora
            pergunta.atualizada_em = agora
            db.flush()
            db.commit()
        except Exception:
            db.rollback()
            raise

    def resposta_classica(self, pergunta: Pergunta) -> dict:
        return _resposta_classica(pergunta)


meu_conteudo_perguntas_service = MeuConteudoPerguntasService()
