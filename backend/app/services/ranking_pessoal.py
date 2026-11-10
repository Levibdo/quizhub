from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.conteudo import MODO_QUIZ_CLASSICO, ORIGEM_USUARIO
from app.models import Categoria, Jogador, Partida
from app.schemas.ranking_pessoal import (
    CategoriaRankingPessoal,
    PartidaRankingPessoal,
)


class RankingPessoalService:
    def listar(
        self, db: Session, usuario_id: UUID
    ) -> list[CategoriaRankingPessoal]:
        categorias = list(
            db.scalars(
                select(Categoria)
                .where(
                    Categoria.usuario_id == usuario_id,
                    Categoria.origem == ORIGEM_USUARIO,
                    Categoria.modo == MODO_QUIZ_CLASSICO,
                )
                .order_by(Categoria.criada_em.asc(), Categoria.id.asc())
            )
        )
        if not categorias:
            return []

        categoria_ids = [categoria.id for categoria in categorias]
        finalizacao_ausente = case(
            (Partida.finalizada_em.is_(None), 1), else_=0
        )
        linhas = db.execute(
            select(
                Partida.categoria_id,
                Partida.id.label("partida_id"),
                Partida.pontuacao,
            )
            .join(Jogador, Jogador.id == Partida.jogador_id)
            .where(
                Partida.categoria_id.in_(categoria_ids),
                Partida.status == "FINALIZADA",
                Jogador.usuario_id == usuario_id,
            )
            .order_by(
                Partida.categoria_id.asc(),
                Partida.pontuacao.desc(),
                finalizacao_ausente.asc(),
                Partida.finalizada_em.asc(),
                Partida.id.asc(),
            )
        ).mappings()

        por_categoria: dict[UUID, list[PartidaRankingPessoal]] = {
            categoria.id: [] for categoria in categorias
        }
        for linha in linhas:
            partidas = por_categoria[linha["categoria_id"]]
            partidas.append(
                PartidaRankingPessoal(
                    posicao=len(partidas) + 1,
                    partida_id=linha["partida_id"],
                    pontuacao=linha["pontuacao"],
                )
            )

        return [
            CategoriaRankingPessoal(
                categoria_id=categoria.id,
                categoria_nome=categoria.nome,
                partidas=por_categoria[categoria.id],
            )
            for categoria in categorias
        ]


ranking_pessoal_service = RankingPessoalService()
