import unittest
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    CatalogoOficial, Categoria, CategoriaOficialVersao,
    FontePerguntaNemPatoOficial,
    FontePerguntaOficial, Pergunta, PerguntaNemPato,
)
from app.services.catalogos_oficiais import (
    CatalogoOficialConflitante, CatalogosOficiaisService,
    predicado_catalogo_ativo,
)
from app.services.validador_catalogos_oficiais import (
    CatalogoNemPatoEditorial, CatalogoQuizEditorial,
)
from tests.test_catalogos_oficiais import catalogo_nem_pato, catalogo_quiz


class TestPersistenciaCatalogosOficiais(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        for slug in ("geral", "tecnologia", "matematica", "entretenimento"):
            self.db.add(Categoria(
                id=uuid4(), slug=slug, nome=slug.title(), modo="QUIZ_CLASSICO",
                origem="OFICIAL", ativa=True,
            ))
        self.db.add(Categoria(
            id=uuid4(), slug="macabro", nome="Macabro", modo="NEM_A_PATO",
            origem="OFICIAL", ativa=True,
        ))
        self.db.flush()
        geral = self.db.scalar(select(Categoria).where(Categoria.slug == "geral"))
        self.legada = Pergunta(
            id=1, categoria_id=geral.id, enunciado="Pergunta legada?",
            alternativa_a="A", alternativa_b="B", alternativa_c="C",
            alternativa_d="D", alternativa_correta=0, explicacao="Legada",
            dificuldade="FACIL", origem="OFICIAL", ativa=True,
        )
        self.db.add(self.legada)
        self.db.commit()
        self.servico = CatalogosOficiaisService()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def quiz(versao=2):
        bruto = catalogo_quiz()
        bruto["catalogo_id"] = "quiz_classico"
        bruto["versao"] = versao
        return CatalogoQuizEditorial.model_validate(bruto)

    @staticmethod
    def nem_pato(versao=1):
        bruto = catalogo_nem_pato()
        bruto["catalogo_id"] = "nem_a_pato_macabro"
        bruto["versao"] = versao
        return CatalogoNemPatoEditorial.model_validate(bruto)

    def test_preparacao_quiz_persiste_ids_fontes_e_e_idempotente(self):
        documento = self.quiz()
        resultado = self.servico._preparar_quiz(self.db, documento, "a" * 64)
        self.db.commit()
        self.assertEqual(resultado.criadas, 400)
        self.assertEqual(self.db.scalar(select(func.count(Pergunta.id))), 401)
        self.assertEqual(
            self.db.scalar(select(func.count(FontePerguntaOficial.id))), 400
        )
        pergunta = self.db.scalar(select(Pergunta).where(
            Pergunta.id_editorial == "qc-geral-001"
        ))
        self.assertEqual(pergunta.fontes_editoriais[0].titulo, "Fonte institucional 1")
        self.assertIsNotNone(pergunta.categoria_versao_id)
        self.assertEqual(pergunta.categoria_versao.catalogo_oficial_id, pergunta.catalogo_oficial_id)
        self.assertEqual(pergunta.categoria_versao.categoria_id, pergunta.categoria_id)
        self.assertEqual(
            self.db.scalar(select(func.count(CategoriaOficialVersao.id)).where(
                CategoriaOficialVersao.catalogo_oficial_id == pergunta.catalogo_oficial_id
            )),
            4,
        )
        self.assertIsNone(self.db.get(Pergunta, 1).catalogo_oficial_id)

        repeticao = self.servico._preparar_quiz(self.db, documento, "a" * 64)
        self.assertEqual((repeticao.criadas, repeticao.existentes), (0, 400))
        with self.assertRaises(CatalogoOficialConflitante):
            self.servico._preparar_quiz(self.db, documento, "b" * 64)

    def test_preparacao_nem_pato_persiste_todas_as_fontes_e_e_idempotente(self):
        bruto = catalogo_nem_pato()
        bruto["catalogo_id"] = "nem_a_pato_macabro"
        bruto["categoria"]["perguntas"][0]["fontes"].append({
            "titulo": "Segunda fonte",
            "url": "https://example.org/fontes/segunda",
            "acessada_em": "2026-10-14",
        })
        documento = CatalogoNemPatoEditorial.model_validate(bruto)
        resultado = self.servico._preparar_nem_pato(
            self.db, documento, "c" * 64
        )
        self.db.commit()
        self.assertEqual(resultado.criadas, 100)
        self.assertEqual(
            self.db.scalar(select(func.count(FontePerguntaNemPatoOficial.id))), 101
        )
        pergunta = self.db.scalar(select(PerguntaNemPato).where(
            PerguntaNemPato.id_editorial == "np-macabro-001"
        ))
        self.assertEqual(len(pergunta.fontes_editoriais), 2)
        self.assertIsNotNone(pergunta.categoria_versao_id)
        self.assertEqual(pergunta.categoria_versao.catalogo_oficial_id, pergunta.catalogo_oficial_id)
        self.assertEqual(pergunta.categoria_versao.categoria_id, pergunta.categoria_id)
        esperado = documento.categoria.perguntas[0]
        self.assertEqual(pergunta.tema_editorial, esperado.tema_editorial)
        self.assertEqual(pergunta.natureza_resposta, esperado.natureza_resposta)
        self.assertEqual(
            pergunta.qualificacao_estimativa,
            esperado.qualificacao_estimativa,
        )
        repeticao = self.servico._preparar_nem_pato(
            self.db, documento, "c" * 64
        )
        self.assertEqual((repeticao.criadas, repeticao.existentes), (0, 100))

    def test_rollback_da_transacao_nao_deixa_catalogo_parcial(self):
        self.servico._preparar_quiz(self.db, self.quiz(), "d" * 64)
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(func.count(CatalogoOficial.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(Pergunta.id))), 1)
        self.assertIsNotNone(self.db.get(Pergunta, 1))

    def test_ativacao_reversao_e_isolamento_entre_versoes(self):
        versao_2 = self.quiz(2)
        self.servico._preparar_quiz(self.db, versao_2, "e" * 64)
        bruto_3 = catalogo_quiz()
        bruto_3["catalogo_id"] = "quiz_classico"
        bruto_3["versao"] = 3
        for categoria in bruto_3["categorias"]:
            for pergunta in categoria["perguntas"]:
                pergunta["id_editorial"] += "-v3"
                pergunta["enunciado"] += " Versão três."
        versao_3 = CatalogoQuizEditorial.model_validate(bruto_3)
        self.servico._preparar_quiz(self.db, versao_3, "f" * 64)

        self.servico.ativar(self.db, "quiz_classico", 2)
        selecionadas = self.db.scalars(select(Pergunta).where(
            predicado_catalogo_ativo(Pergunta, "QUIZ_CLASSICO")
        )).all()
        self.assertEqual(len(selecionadas), 400)
        self.assertTrue(all(not p.id_editorial.endswith("-v3") for p in selecionadas))

        self.servico.ativar(self.db, "quiz_classico", 3)
        selecionadas = self.db.scalars(select(Pergunta).where(
            predicado_catalogo_ativo(Pergunta, "QUIZ_CLASSICO")
        )).all()
        self.assertEqual(len(selecionadas), 400)
        self.assertTrue(all(p.id_editorial.endswith("-v3") for p in selecionadas))

        self.servico.ativar(self.db, "quiz_classico", 2)
        estados = dict(self.db.execute(select(
            CatalogoOficial.versao, CatalogoOficial.status
        )).all())
        self.assertEqual(estados, {2: "ATIVO", 3: "ARQUIVADO"})

        self.servico.reverter_para_legado(self.db, "QUIZ_CLASSICO")
        selecionadas = self.db.scalars(select(Pergunta).where(
            predicado_catalogo_ativo(Pergunta, "QUIZ_CLASSICO")
        )).all()
        self.assertEqual(selecionadas, [])

    def test_sem_catalogo_ativo_nao_seleciona_legado(self):
        self.servico._preparar_quiz(self.db, self.quiz(), "1" * 64)
        selecionadas = self.db.scalars(select(Pergunta).where(
            predicado_catalogo_ativo(Pergunta, "QUIZ_CLASSICO")
        )).all()
        self.assertEqual(selecionadas, [])


if __name__ == "__main__":
    unittest.main()
