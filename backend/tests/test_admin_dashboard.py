import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    CatalogoOficial,
    Categoria,
    Jogador,
    Partida,
    PartidaNemPato,
    Pergunta,
    PerguntaNemPato,
    SalaNemPato,
    Temporada,
    Usuario,
)
from app.nem_a_pato import PartidaNemPatoStatus
from app.services.dashboard_administrativo import obter_dashboard_administrativo


class TestDashboardAdministrativo(unittest.TestCase):
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

    def test_banco_vazio_retorna_indicadores_zerados(self):
        dados = obter_dashboard_administrativo(self.db, limite_auditoria=20)
        self.assertEqual(dados["indicadores"]["usuarios"], {
            "total": 0, "ativos": 0,
        })
        self.assertEqual(dados["indicadores"]["partidas"]["total"], 0)
        self.assertEqual(dados["indicadores"]["perguntas"]["total"], 0)
        self.assertEqual(dados["indicadores"]["categorias"]["total"], 0)
        self.assertEqual(dados["indicadores"]["catalogos_oficiais_ativos"], 0)
        self.assertIsNone(dados["temporada_ativa"])

    def test_conta_conteudo_atual_e_separa_partidas_por_modo(self):
        agora = datetime.now(timezone.utc)
        admin = Usuario(
            nome="Admin", email="admin-dashboard@example.com",
            senha_hash="hash-artificial", perfil="ADMIN", ativo=True,
        )
        inativo = Usuario(
            nome="Inativo", email="inativo-dashboard@example.com",
            senha_hash="hash-artificial", perfil="JOGADOR", ativo=False,
        )
        self.db.add_all([admin, inativo])
        self.db.flush()
        categoria_quiz = Categoria(
            slug="geral-dashboard", nome="Geral dashboard",
            modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=True,
        )
        categoria_nem = Categoria(
            slug="macabro-dashboard", nome="Macabro dashboard",
            modo="NEM_A_PATO", origem="OFICIAL", ativa=True,
        )
        categoria_privada = Categoria(
            slug="privada-dashboard", nome="Privada dashboard",
            modo="QUIZ_CLASSICO", origem="USUARIO", usuario_id=admin.id,
            ativa=True,
        )
        categoria_excluida = Categoria(
            slug="excluida-dashboard", nome="Excluída dashboard",
            modo="QUIZ_CLASSICO", origem="USUARIO", usuario_id=admin.id,
            ativa=False, excluida_em=agora,
        )
        self.db.add_all([
            categoria_quiz, categoria_nem, categoria_privada, categoria_excluida,
        ])
        self.db.flush()
        self.db.add_all([
            Pergunta(
                id=98001, categoria_id=categoria_quiz.id, enunciado="Oficial?",
                alternativa_a="A", alternativa_b="B", alternativa_c="C",
                alternativa_d="D", alternativa_correta=0, explicacao="Teste",
                origem="OFICIAL", ativa=True,
            ),
            Pergunta(
                id=98002, categoria_id=categoria_privada.id, enunciado="Privada?",
                alternativa_a="A", alternativa_b="B", alternativa_c="C",
                alternativa_d="D", alternativa_correta=0, explicacao="Teste",
                origem="USUARIO", usuario_id=admin.id, ativa=True,
            ),
            Pergunta(
                id=98003, categoria_id=categoria_excluida.id, enunciado="Excluída?",
                alternativa_a="A", alternativa_b="B", alternativa_c="C",
                alternativa_d="D", alternativa_correta=0, explicacao="Teste",
                origem="USUARIO", usuario_id=admin.id, ativa=False,
                excluida_em=agora,
            ),
            PerguntaNemPato(
                categoria_id=categoria_nem.id, enunciado="Quantos?",
                resposta_numerica=1, explicacao="Teste", origem="OFICIAL",
                ativa=True,
            ),
        ])
        jogador = Jogador(nome="Visitante")
        sala = SalaNemPato(codigo="DASHBOARD")
        temporada = Temporada(
            numero=1, nome="Temporada 1", status="ATIVA", inicia_em=agora,
        )
        catalogo = CatalogoOficial(
            catalogo_id="quiz_dashboard", versao=1, modo="QUIZ_CLASSICO",
            status="ATIVO", sha256="a" * 64, ativado_em=agora,
        )
        self.db.add_all([jogador, sala, temporada, catalogo])
        self.db.flush()
        self.db.add_all([
            Partida(
                jogador_id=jogador.id, categoria_id=categoria_quiz.id,
                temporada_id=temporada.id, status="FINALIZADA",
            ),
            Partida(
                jogador_id=jogador.id, categoria_id=categoria_quiz.id,
                temporada_id=temporada.id, status="EM_ANDAMENTO",
            ),
            PartidaNemPato(
                sala_id=sala.id, categoria_id=categoria_nem.id, numero=1,
                status=PartidaNemPatoStatus.FINALIZADA,
            ),
            PartidaNemPato(
                sala_id=sala.id, categoria_id=categoria_nem.id, numero=2,
                status=PartidaNemPatoStatus.CANCELADA,
            ),
        ])
        self.db.commit()

        dados = obter_dashboard_administrativo(self.db, limite_auditoria=20)
        indicadores = dados["indicadores"]
        self.assertEqual(indicadores["usuarios"], {"total": 2, "ativos": 1})
        self.assertEqual(indicadores["categorias"], {
            "total": 3, "oficiais": 2, "privadas": 1,
        })
        self.assertEqual(indicadores["perguntas"], {
            "total": 3, "oficiais": 2, "privadas": 1,
        })
        self.assertEqual(indicadores["partidas"], {
            "total": 4,
            "concluidas": 2,
            "quiz_classico": {"total": 2, "concluidas": 1},
            "nem_a_pato": {"total": 2, "concluidas": 1},
        })
        self.assertEqual(indicadores["catalogos_oficiais_ativos"], 1)
        self.assertEqual(dados["temporada_ativa"].id, temporada.id)


if __name__ == "__main__":
    unittest.main()
