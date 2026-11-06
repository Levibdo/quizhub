import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    CatalogoOficial, Categoria, CategoriaOficialVersao,
    FontePerguntaNemPatoOficial,
    FontePerguntaOficial, Pergunta, PerguntaNemPato,
)
from app.services.validador_catalogos_oficiais import (
    CatalogoNemPatoEditorial, CatalogoQuizEditorial, validar_catalogos,
)


class CatalogoOficialInvalido(ValueError):
    pass


class CatalogoOficialConflitante(ValueError):
    pass


@dataclass(frozen=True)
class ResultadoPreparacaoCatalogo:
    catalogo_id: str
    versao: int
    modo: str
    criadas: int
    existentes: int


def predicado_catalogo_ativo(modelo, modo: str):
    consulta = select(CatalogoOficial.id).where(
        CatalogoOficial.modo == modo,
        CatalogoOficial.status == "ATIVO",
    )
    return modelo.catalogo_oficial_id == consulta.scalar_subquery()


ERRO_CATALOGO_OFICIAL_INATIVO = {
    "codigo": "CATALOGO_OFICIAL_INATIVO",
    "mensagem": (
        "Este modo de jogo está temporariamente indisponível. "
        "Nenhum catálogo de perguntas está ativo."
    ),
}


def exigir_catalogo_ativo(db: Session, modo: str) -> CatalogoOficial:
    consulta = select(CatalogoOficial).where(
        CatalogoOficial.modo == modo,
        CatalogoOficial.status == "ATIVO",
    )
    if db.get_bind().dialect.name == "postgresql":
        # O lock compartilhado impede que uma ativação/reversão concorrente
        # altere o catálogo até a seleção e persistência das perguntas.
        consulta = consulta.with_for_update(read=True)
    catalogo = db.scalar(consulta)
    if catalogo is None:
        raise HTTPException(
            status_code=503,
            detail=ERRO_CATALOGO_OFICIAL_INATIVO,
        )
    return catalogo


class CatalogosOficiaisService:
    @staticmethod
    def _documento(caminho: Path, modelo):
        return modelo.model_validate(json.loads(caminho.read_text(encoding="utf-8")))

    @staticmethod
    def _categorias(db: Session, modo: str) -> dict[str, Categoria]:
        return {
            item.slug: item for item in db.scalars(select(Categoria).where(
                Categoria.modo == modo,
                Categoria.origem == "OFICIAL",
                Categoria.excluida_em.is_(None),
            ))
        }

    @staticmethod
    def _catalogo_existente(db, documento, sha256):
        existente = db.scalar(select(CatalogoOficial).where(
            CatalogoOficial.catalogo_id == documento.catalogo_id,
            CatalogoOficial.versao == documento.versao,
        ))
        if existente is not None and existente.sha256 != sha256:
            raise CatalogoOficialConflitante(
                "a mesma identidade e versão já existem com conteúdo diferente"
            )
        return existente

    @staticmethod
    def _criar_versoes_categorias(
        db: Session,
        catalogo: CatalogoOficial,
        categorias: dict[str, Categoria],
        slugs: list[str],
    ) -> dict[str, CategoriaOficialVersao]:
        """Materializa categorias da versão durante importações completas.

        A partir da 0023, mesmo o fluxo de importação integral precisa produzir
        perguntas versionadas. O método não associa conteúdo histórico sem
        proveniência e não altera versões já publicadas.
        """
        db.flush()
        versoes = {}
        for slug in slugs:
            categoria = categorias[slug]
            versao = CategoriaOficialVersao(
                categoria_id=categoria.id,
                catalogo_oficial_id=catalogo.id,
                modo=catalogo.modo,
                slug=categoria.slug,
                nome=categoria.nome,
                descricao=categoria.descricao,
                ativa=categoria.ativa,
                origem_backfill=False,
            )
            db.add(versao)
            versoes[slug] = versao
        db.flush()
        return versoes

    def preparar_quiz(self, db: Session, caminho: str | Path):
        caminho = Path(caminho)
        relatorio = validar_catalogos(quiz=caminho)
        if not relatorio.valido:
            raise CatalogoOficialInvalido(str(relatorio.erros))
        documento = self._documento(caminho, CatalogoQuizEditorial)
        return self._preparar_quiz(db, documento, relatorio.hashes[str(caminho)])

    def _preparar_quiz(self, db, documento, sha256):
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("LOCK TABLE catalogos_oficiais, perguntas IN SHARE ROW EXCLUSIVE MODE"))
        existente = self._catalogo_existente(db, documento, sha256)
        if existente is not None:
            total = db.scalar(select(func.count(Pergunta.id)).where(
                Pergunta.catalogo_oficial_id == existente.id
            ))
            if total != 400:
                raise CatalogoOficialConflitante("catálogo idempotente está incompleto")
            return ResultadoPreparacaoCatalogo(
                documento.catalogo_id, documento.versao, documento.modo, 0, total
            )
        categorias = self._categorias(db, documento.modo)
        ausentes = sorted({c.slug for c in documento.categorias} - set(categorias))
        if ausentes:
            raise CatalogoOficialInvalido("categorias oficiais ausentes: " + ", ".join(ausentes))
        catalogo = CatalogoOficial(
            catalogo_id=documento.catalogo_id, versao=documento.versao,
            modo=documento.modo, status="PREPARADO", sha256=sha256,
        )
        db.add(catalogo)
        versoes_categorias = self._criar_versoes_categorias(
            db, catalogo, categorias, [item.slug for item in documento.categorias]
        )
        proximo_id = (db.scalar(select(func.max(Pergunta.id))) or 0) + 1
        for categoria in documento.categorias:
            for item in categoria.perguntas:
                pergunta = Pergunta(
                    id=proximo_id, categoria_id=categorias[categoria.slug].id,
                    enunciado=item.enunciado,
                    alternativa_a=item.alternativas[0], alternativa_b=item.alternativas[1],
                    alternativa_c=item.alternativas[2], alternativa_d=item.alternativas[3],
                    alternativa_correta=item.resposta_correta,
                    explicacao=item.explicacao, dificuldade=item.dificuldade,
                    origem="OFICIAL", ativa=True, catalogo_oficial=catalogo,
                    categoria_versao=versoes_categorias[categoria.slug],
                    id_editorial=item.id_editorial,
                )
                pergunta.fontes_editoriais = [
                    FontePerguntaOficial(
                        ordem=ordem, titulo=fonte.titulo, url=str(fonte.url),
                        acessada_em=fonte.acessada_em,
                    )
                    for ordem, fonte in enumerate(item.fontes, 1)
                ]
                db.add(pergunta)
                proximo_id += 1
        db.flush()
        return ResultadoPreparacaoCatalogo(
            documento.catalogo_id, documento.versao, documento.modo, 400, 0
        )

    def preparar_nem_pato(self, db: Session, caminho: str | Path):
        caminho = Path(caminho)
        relatorio = validar_catalogos(nem_pato=caminho)
        if not relatorio.valido:
            raise CatalogoOficialInvalido(str(relatorio.erros))
        documento = self._documento(caminho, CatalogoNemPatoEditorial)
        return self._preparar_nem_pato(
            db, documento, relatorio.hashes[str(caminho)]
        )

    def _preparar_nem_pato(self, db, documento, sha256):
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text(
                "LOCK TABLE catalogos_oficiais, perguntas_nem_pato "
                "IN SHARE ROW EXCLUSIVE MODE"
            ))
        existente = self._catalogo_existente(db, documento, sha256)
        if existente is not None:
            total = db.scalar(select(func.count(PerguntaNemPato.id)).where(
                PerguntaNemPato.catalogo_oficial_id == existente.id
            ))
            if total != 100:
                raise CatalogoOficialConflitante("catálogo idempotente está incompleto")
            return ResultadoPreparacaoCatalogo(
                documento.catalogo_id, documento.versao, documento.modo, 0, total
            )
        categorias = self._categorias(db, documento.modo)
        categoria = categorias.get(documento.categoria.slug)
        if categoria is None:
            raise CatalogoOficialInvalido(
                f"categoria oficial ausente: {documento.categoria.slug}"
            )
        catalogo = CatalogoOficial(
            catalogo_id=documento.catalogo_id, versao=documento.versao,
            modo=documento.modo, status="PREPARADO", sha256=sha256,
        )
        db.add(catalogo)
        versoes_categorias = self._criar_versoes_categorias(
            db, catalogo, categorias, [documento.categoria.slug]
        )
        for item in documento.categoria.perguntas:
            primeira = item.fontes[0]
            pergunta = PerguntaNemPato(
                categoria_id=categoria.id, enunciado=item.enunciado,
                resposta_numerica=item.resposta_numerica, unidade=item.unidade,
                explicacao=item.explicacao, fonte=primeira.titulo,
                fonte_url=str(primeira.url), fonte_acessada_em=primeira.acessada_em,
                origem="OFICIAL", ativa=True, catalogo_oficial=catalogo,
                categoria_versao=versoes_categorias[documento.categoria.slug],
                id_editorial=item.id_editorial,
                tema_editorial=item.tema_editorial,
                natureza_resposta=item.natureza_resposta,
                qualificacao_estimativa=item.qualificacao_estimativa,
            )
            pergunta.fontes_editoriais = [
                FontePerguntaNemPatoOficial(
                    ordem=ordem, titulo=fonte.titulo, url=str(fonte.url),
                    acessada_em=fonte.acessada_em,
                )
                for ordem, fonte in enumerate(item.fontes, 1)
            ]
            db.add(pergunta)
        db.flush()
        return ResultadoPreparacaoCatalogo(
            documento.catalogo_id, documento.versao, documento.modo, 100, 0
        )

    def ativar(self, db: Session, catalogo_id: str, versao: int) -> CatalogoOficial:
        agora = datetime.now(timezone.utc)
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text(
                "LOCK TABLE catalogos_oficiais IN SHARE ROW EXCLUSIVE MODE"
            ))
        catalogos = list(db.scalars(
            select(CatalogoOficial).where(
                CatalogoOficial.catalogo_id == catalogo_id
            ).with_for_update()
        ))
        alvo = next((c for c in catalogos if c.versao == versao), None)
        if alvo is None:
            raise CatalogoOficialInvalido("catálogo ou versão inexistente")
        modelo, esperado = (
            (Pergunta, 400) if alvo.modo == "QUIZ_CLASSICO"
            else (PerguntaNemPato, 100)
        )
        total = db.scalar(select(func.count(modelo.id)).where(
            modelo.catalogo_oficial_id == alvo.id
        ))
        sem_fontes = db.scalar(select(func.count(modelo.id)).where(
            modelo.catalogo_oficial_id == alvo.id,
            ~modelo.fontes_editoriais.any(),
        ))
        if total != esperado or sem_fontes:
            raise CatalogoOficialInvalido("catálogo incompleto ou sem fontes")
        ativos = list(db.scalars(select(CatalogoOficial).where(
            CatalogoOficial.modo == alvo.modo,
            CatalogoOficial.status == "ATIVO",
        ).with_for_update()))
        for atual in ativos:
            if atual.id != alvo.id:
                atual.status = "ARQUIVADO"
                atual.arquivado_em = agora
        # Libera a unicidade parcial antes de promover outra versão. Tudo ocorre
        # na mesma transação e sob os locks acima, portanto não há janela externa
        # sem catálogo ativo.
        db.flush()
        alvo.status = "ATIVO"
        alvo.ativado_em = agora
        alvo.arquivado_em = None
        db.flush()
        return alvo

    def reverter_para_legado(self, db: Session, modo: str) -> None:
        if modo not in {"QUIZ_CLASSICO", "NEM_A_PATO"}:
            raise CatalogoOficialInvalido("modo de catálogo inválido")
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text(
                "LOCK TABLE catalogos_oficiais IN SHARE ROW EXCLUSIVE MODE"
            ))
        ativos = list(db.scalars(select(CatalogoOficial).where(
            CatalogoOficial.modo == modo,
            CatalogoOficial.status == "ATIVO",
        ).with_for_update()))
        agora = datetime.now(timezone.utc)
        for catalogo in ativos:
            catalogo.status = "ARQUIVADO"
            catalogo.arquivado_em = agora
        db.flush()


catalogos_oficiais_service = CatalogosOficiaisService()
