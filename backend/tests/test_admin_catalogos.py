import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import CatalogoOficial, Categoria, Pergunta, PerguntaNemPato
from app.services.consulta_catalogos_oficiais import consultar_catalogos_oficiais


class TestConsultaCatalogosOficiais(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_lista_vazia(self):
        self.assertEqual(consultar_catalogos_oficiais(self.db), [])

    def test_separa_ativacao_e_conta_perguntas_dos_dois_modos(self):
        agora = datetime.now(timezone.utc)
        quiz = CatalogoOficial(
            catalogo_id="quiz_classico_v2", versao=2,
            modo="QUIZ_CLASSICO", status="ATIVO", sha256="a" * 64,
            ativado_em=agora,
        )
        nem_pato = CatalogoOficial(
            catalogo_id="nem_a_pato_macabro_v1", versao=1,
            modo="NEM_A_PATO", status="ARQUIVADO", sha256="b" * 64,
            arquivado_em=agora,
        )
        categoria_quiz = Categoria(
            slug="geral-catalogos", nome="Geral catálogos",
            modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=True,
        )
        categoria_nem = Categoria(
            slug="macabro-catalogos", nome="Macabro catálogos",
            modo="NEM_A_PATO", origem="OFICIAL", ativa=True,
        )
        self.db.add_all([quiz, nem_pato, categoria_quiz, categoria_nem])
        self.db.flush()
        for identificador in (99101, 99102):
            self.db.add(Pergunta(
                id=identificador, categoria_id=categoria_quiz.id,
                enunciado="Pergunta?", alternativa_a="A", alternativa_b="B",
                alternativa_c="C", alternativa_d="D", alternativa_correta=0,
                explicacao="Explicação", origem="OFICIAL", ativa=True,
                catalogo_oficial_id=quiz.id,
                id_editorial=f"GER-{identificador}",
            ))
        self.db.add(PerguntaNemPato(
            categoria_id=categoria_nem.id, enunciado="Quantos?",
            resposta_numerica=1, explicacao="Explicação", origem="OFICIAL",
            ativa=True, catalogo_oficial_id=nem_pato.id, id_editorial="MAC-001",
        ))
        self.db.commit()

        registros = consultar_catalogos_oficiais(self.db)
        self.assertEqual(len(registros), 2)
        por_id = {item["catalogo_id"]: item for item in registros}
        self.assertEqual(por_id["quiz_classico_v2"]["quantidade_perguntas"], 2)
        self.assertEqual(por_id["quiz_classico_v2"]["situacao_ativacao"], "ATIVO")
        self.assertEqual(por_id["quiz_classico_v2"]["status_registro"], "ATIVO")
        self.assertIsNone(por_id["quiz_classico_v2"]["estado_editorial"])
        self.assertEqual(por_id["nem_a_pato_macabro_v1"]["quantidade_perguntas"], 1)
        self.assertEqual(por_id["nem_a_pato_macabro_v1"]["situacao_ativacao"], "INATIVO")
        self.assertEqual(por_id["nem_a_pato_macabro_v1"]["status_registro"], "ARQUIVADO")
        self.assertNotIn("sha256", por_id["quiz_classico_v2"])


if __name__ == "__main__":
    unittest.main()
