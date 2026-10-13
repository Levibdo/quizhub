from uuid import UUID

from sqlalchemy import String, case, cast, func, literal, select
from sqlalchemy.orm import Session

from app.models import Categoria, Jogador, Partida
from app.schemas.ranking import CategoriaRankingPublica, ItemRankingPublico


class RankingService:
    @staticmethod
    def _filtro_categoria(categoria: str):
        try:
            categoria_uuid = UUID(categoria)
        except (TypeError, ValueError, AttributeError):
            categoria_uuid = None
        if categoria_uuid is not None:
            return Categoria.id == categoria_uuid
        return Categoria.slug == categoria

    def listar(
        self,
        db: Session,
        *,
        categoria: str | None = None,
        limit: int = 10,
    ) -> list[ItemRankingPublico]:
        if limit < 1 or limit > 100:
            raise ValueError("limit deve estar entre 1 e 100")
        identidade = case(
            (
                Jogador.usuario_id.is_not(None),
                literal("usuario:") + cast(Jogador.usuario_id, String),
            ),
            (
                Jogador.visitante_id.is_not(None),
                literal("visitante:") + cast(Jogador.visitante_id, String),
            ),
            else_=literal("historico:") + cast(Jogador.id, String),
        )
        finalizacao_ausente = case(
            (Partida.finalizada_em.is_(None), 1),
            else_=0,
        )
        criterios = (
            Partida.pontuacao.desc(),
            Partida.acertos.desc(),
            finalizacao_ausente.asc(),
            Partida.finalizada_em.asc(),
            Partida.id.asc(),
        )
        ordem_identidade = func.row_number().over(
            partition_by=identidade,
            order_by=criterios,
        ).label("ordem_identidade")

        consulta = (
            select(
                Partida.id.label("partida_id"),
                Jogador.nome.label("jogador"),
                Categoria.id.label("categoria_id"),
                Categoria.slug.label("categoria_slug"),
                Categoria.nome.label("categoria_nome"),
                Partida.pontuacao,
                Partida.acertos,
                Partida.erros,
                Partida.finalizada_em,
                finalizacao_ausente.label("finalizacao_ausente"),
                ordem_identidade,
            )
            .join(Jogador, Jogador.id == Partida.jogador_id)
            .join(Categoria, Categoria.id == Partida.categoria_id)
            .where(
                Partida.status == "FINALIZADA",
                Categoria.modo == "QUIZ_CLASSICO",
                Categoria.origem == "OFICIAL",
                Categoria.ativa.is_(True),
                Categoria.excluida_em.is_(None),
            )
        )
        if categoria is not None:
            consulta = consulta.where(self._filtro_categoria(categoria))
        candidatas = consulta.subquery()

        melhores = (
            select(candidatas)
            .where(candidatas.c.ordem_identidade == 1)
            .order_by(
                candidatas.c.pontuacao.desc(),
                candidatas.c.acertos.desc(),
                candidatas.c.finalizacao_ausente.asc(),
                candidatas.c.finalizada_em.asc(),
                candidatas.c.partida_id.asc(),
            )
            .limit(limit)
        )
        linhas = db.execute(melhores).mappings().all()
        return [
            ItemRankingPublico(
                posicao=posicao,
                jogador=linha["jogador"],
                categoria=CategoriaRankingPublica(
                    id=linha["categoria_id"],
                    slug=linha["categoria_slug"],
                    nome=linha["categoria_nome"],
                ),
                pontuacao=linha["pontuacao"],
                acertos=linha["acertos"],
                erros=linha["erros"],
                finalizada_em=linha["finalizada_em"],
            )
            for posicao, linha in enumerate(linhas, start=1)
        ]


ranking_service = RankingService()
