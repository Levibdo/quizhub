import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    CatalogoOficial,
    Categoria,
    FontePerguntaNemPatoOficial,
    FontePerguntaOficial,
    Pergunta,
    PerguntaNemPato,
    Usuario,
)
from app.services.consulta_perguntas_oficiais import (
    consultar_perguntas_oficiais,
    obter_pergunta_oficial,
    opcoes_perguntas_oficiais,
)


class TestConsultaPerguntasOficiais(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        usuario = Usuario(
            nome="Proprietário", email="owner-c2@example.com",
            senha_hash="hash-artificial", perfil="JOGADOR",
        )
        self.db.add(usuario)
        self.db.flush()
        self.quiz = CatalogoOficial(
            catalogo_id="quiz_c2", versao=2, modo="QUIZ_CLASSICO",
            status="ATIVO", sha256="a" * 64,
        )
        self.nem = CatalogoOficial(
            catalogo_id="nem_c2", versao=1, modo="NEM_A_PATO",
            status="PREPARADO", sha256="b" * 64,
        )
        self.cat_quiz = Categoria(
            slug="geral-c2", nome="Geral C2", modo="QUIZ_CLASSICO",
            origem="OFICIAL", ativa=True,
        )
        self.cat_nem = Categoria(
            slug="macabro-c2", nome="Macabro C2", modo="NEM_A_PATO",
            origem="OFICIAL", ativa=True,
        )
        self.cat_privada = Categoria(
            slug="privada-c2", nome="Privada C2", modo="QUIZ_CLASSICO",
            origem="USUARIO", usuario_id=usuario.id, ativa=True,
        )
        self.db.add_all([
            self.quiz, self.nem, self.cat_quiz, self.cat_nem, self.cat_privada,
        ])
        self.db.flush()
        self.pergunta_quiz = Pergunta(
            id=99301, categoria_id=self.cat_quiz.id,
            enunciado="Qual evento documentado ocorreu?",
            alternativa_a="A", alternativa_b="B", alternativa_c="C",
            alternativa_d="D", alternativa_correta=2,
            explicacao="Explicação oficial C2.", dificuldade="MEDIA",
            origem="OFICIAL", ativa=True, catalogo_oficial_id=self.quiz.id,
            id_editorial="GER-C2-001",
        )
        self.pergunta_nem = PerguntaNemPato(
            categoria_id=self.cat_nem.id,
            enunciado="Quantos registros foram documentados?",
            resposta_numerica=9_007_199_254_740_993,
            unidade="registros", explicacao="Explicação numérica C2.",
            origem="OFICIAL", ativa=False, catalogo_oficial_id=self.nem.id,
            id_editorial="MAC-C2-001", natureza_resposta="EXATA",
        )
        self.pergunta_privada = Pergunta(
            id=99302, categoria_id=self.cat_privada.id,
            enunciado="Pergunta privada invisível?", alternativa_a="A",
            alternativa_b="B", alternativa_c="C", alternativa_d="D",
            alternativa_correta=0, explicacao="Privada", origem="USUARIO",
            usuario_id=usuario.id, ativa=True,
        )
        self.db.add_all([
            self.pergunta_quiz, self.pergunta_nem, self.pergunta_privada,
        ])
        self.db.flush()
        self.db.add_all([
            FontePerguntaOficial(
                pergunta_id=self.pergunta_quiz.id, ordem=1,
                titulo="Arquivo histórico C2", url="https://example.org/quiz-c2",
                acessada_em=date(2026, 10, 21),
            ),
            FontePerguntaNemPatoOficial(
                pergunta_id=self.pergunta_nem.id, ordem=1,
                titulo="Instituição científica C2",
                url="https://example.org/nem-c2",
                acessada_em=date(2026, 10, 20),
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_pagina_no_sql_ordena_e_isola_conteudo_privado(self):
        primeira = consultar_perguntas_oficiais(
            self.db, pagina=1, limite=1,
        )
        segunda = consultar_perguntas_oficiais(
            self.db, pagina=2, limite=1,
        )
        self.assertEqual(primeira["total"], 2)
        self.assertEqual(primeira["total_paginas"], 2)
        self.assertEqual(len(primeira["itens"]), 1)
        self.assertNotEqual(
            (primeira["itens"][0]["modo"], primeira["itens"][0]["id"]),
            (segunda["itens"][0]["modo"], segunda["itens"][0]["id"]),
        )
        self.assertNotIn("privada", str([primeira, segunda]).lower())

    def test_filtros_combinados_busca_estado_dificuldade_catalogo_e_categoria(self):
        quiz = consultar_perguntas_oficiais(
            self.db, pagina=1, limite=20, modo="QUIZ_CLASSICO",
            catalogo_id=self.quiz.id, versao=2,
            categoria_id=self.cat_quiz.id, ativa=True,
            dificuldade="MEDIA", busca="EVENTO documentado",
        )
        self.assertEqual(quiz["total"], 1)
        self.assertEqual(quiz["itens"][0]["id_editorial"], "GER-C2-001")
        self.assertEqual(consultar_perguntas_oficiais(
            self.db, pagina=1, limite=20, modo="NEM_A_PATO",
            dificuldade="FACIL",
        )["total"], 0)
        self.assertEqual(consultar_perguntas_oficiais(
            self.db, pagina=1, limite=20, ativa=False,
        )["itens"][0]["id_editorial"], "MAC-C2-001")

    def test_detalhes_preservam_respostas_e_fontes(self):
        quiz = obter_pergunta_oficial(
            self.db, modo="QUIZ_CLASSICO", pergunta_id=self.pergunta_quiz.id,
        )
        self.assertEqual(quiz["alternativas"], ["A", "B", "C", "D"])
        self.assertEqual(quiz["alternativa_correta"], 2)
        self.assertEqual(quiz["referencias"][0]["titulo"], "Arquivo histórico C2")
        nem = obter_pergunta_oficial(
            self.db, modo="NEM_A_PATO", pergunta_id=self.pergunta_nem.id,
        )
        self.assertEqual(nem["resposta_numerica"], "9007199254740993")
        self.assertEqual(nem["unidade"], "registros")
        self.assertEqual(nem["referencias"][0]["url"], "https://example.org/nem-c2")
        self.assertIsNone(obter_pergunta_oficial(
            self.db, modo="QUIZ_CLASSICO", pergunta_id=self.pergunta_privada.id,
        ))

    def test_opcoes_contem_somente_categorias_oficiais(self):
        opcoes = opcoes_perguntas_oficiais(self.db)
        self.assertEqual(len(opcoes["catalogos"]), 2)
        self.assertEqual(len(opcoes["categorias"]), 2)
        self.assertNotIn("Privada C2", [item["nome"] for item in opcoes["categorias"]])


if __name__ == "__main__":
    unittest.main()
