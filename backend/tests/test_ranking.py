import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.api.v1.ranking import ranking
from app.main import app
from app.models import Categoria, Jogador, Partida, Usuario
from app.services.ranking import RankingService


class TestRankingGlobal(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.servico = RankingService()
        self.agora = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        self.proximo_id = 1
        with self.sessions() as session:
            dono = Usuario(
                nome="Dona",
                email="dona-ranking@example.com",
                senha_hash="hash-de-teste",
            )
            session.add(dono)
            session.flush()
            self.usuario_id = dono.id
            self.geral_id = uuid4()
            self.tecnologia_id = uuid4()
            self.privada_id = uuid4()
            self.nem_pato_id = uuid4()
            self.inativa_id = uuid4()
            session.add_all([
                Categoria(
                    id=self.geral_id, slug="geral", nome="Geral",
                    modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=True,
                ),
                Categoria(
                    id=self.tecnologia_id, slug="tecnologia", nome="Tecnologia",
                    modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=True,
                ),
                Categoria(
                    id=self.privada_id, slug="privada", nome="Privada",
                    modo="QUIZ_CLASSICO", origem="USUARIO", usuario_id=dono.id,
                    ativa=True,
                ),
                Categoria(
                    id=self.nem_pato_id, slug="geral", nome="Geral NP",
                    modo="NEM_A_PATO", origem="OFICIAL", ativa=True,
                ),
                Categoria(
                    id=self.inativa_id, slug="arquivo", nome="Arquivo",
                    modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=False,
                ),
            ])
            session.commit()

    def tearDown(self):
        self.engine.dispose()

    def adicionar_partida(
        self,
        session,
        *,
        nome,
        pontuacao,
        acertos,
        status="FINALIZADA",
        finalizada_em=None,
        categoria_id=None,
        usuario_id=None,
        visitante_id=None,
        partida_id=None,
    ):
        jogador = Jogador(
            nome=nome,
            usuario_id=usuario_id,
            visitante_id=visitante_id,
        )
        session.add(jogador)
        session.flush()
        identificador = partida_id or UUID(int=self.proximo_id)
        self.proximo_id += 1
        partida = Partida(
            id=identificador,
            jogador_id=jogador.id,
            categoria_id=categoria_id or self.geral_id,
            status=status,
            pontuacao=pontuacao,
            acertos=acertos,
            erros=max(0, 10 - acertos),
            iniciada_em=self.agora - timedelta(minutes=5),
            finalizada_em=(
                self.agora if finalizada_em is None and status == "FINALIZADA"
                else finalizada_em
            ),
        )
        session.add(partida)
        session.flush()
        return partida

    def listar(self, **parametros):
        with self.sessions() as session:
            return self.servico.listar(session, **parametros)

    def test_ranking_vazio_e_consulta_unica(self):
        statements = []

        def registrar(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", registrar)
        try:
            self.assertEqual(self.listar(), [])
        finally:
            event.remove(self.engine, "before_cursor_execute", registrar)
        self.assertEqual(len(statements), 1)

    def test_inclui_finalizada_e_exclui_estados_nao_finalizados(self):
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Final", pontuacao=1200, acertos=8,
            )
            self.adicionar_partida(
                session, nome="Andamento", pontuacao=2000, acertos=10,
                status="EM_ANDAMENTO", finalizada_em=None,
            )
            self.adicionar_partida(
                session, nome="Expirada", pontuacao=1900, acertos=9,
                status="EXPIRADA", finalizada_em=None,
            )
            session.commit()
        resultado = self.listar()
        self.assertEqual([item.jogador for item in resultado], ["Final"])
        self.assertEqual(resultado[0].posicao, 1)
        self.assertEqual(resultado[0].pontuacao, 1200)

    def test_melhor_partida_por_usuario_autenticado(self):
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Nome antigo", pontuacao=800, acertos=6,
                usuario_id=self.usuario_id,
            )
            self.adicionar_partida(
                session, nome="Nome atual", pontuacao=1500, acertos=9,
                usuario_id=self.usuario_id,
            )
            session.commit()
        resultado = self.listar()
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].jogador, "Nome atual")
        self.assertEqual(resultado[0].pontuacao, 1500)

    def test_melhor_partida_por_visitante_persistente(self):
        visitante_id = uuid4()
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Visitante", pontuacao=1000, acertos=7,
                visitante_id=visitante_id,
            )
            self.adicionar_partida(
                session, nome="Visitante", pontuacao=1300, acertos=8,
                visitante_id=visitante_id,
            )
            session.commit()
        resultado = self.listar()
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].pontuacao, 1300)

    def test_nomes_iguais_com_identidades_distintas_nao_sao_agrupados(self):
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Mesmo nome", pontuacao=1100, acertos=7,
                visitante_id=uuid4(),
            )
            self.adicionar_partida(
                session, nome="Mesmo nome", pontuacao=900, acertos=6,
                visitante_id=uuid4(),
            )
            session.commit()
        self.assertEqual(len(self.listar()), 2)

    def test_visitantes_historicos_permanecem_individuais(self):
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Legado", pontuacao=1000, acertos=7,
            )
            self.adicionar_partida(
                session, nome="Legado", pontuacao=900, acertos=6,
            )
            session.commit()
        self.assertEqual(len(self.listar()), 2)

    def test_desempates_usam_acertos_horario_nulos_e_id(self):
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Menos acertos", pontuacao=1000, acertos=7,
                finalizada_em=self.agora - timedelta(hours=3),
            )
            self.adicionar_partida(
                session, nome="Mais acertos", pontuacao=1000, acertos=8,
                finalizada_em=self.agora - timedelta(hours=1),
            )
            self.adicionar_partida(
                session, nome="Mais antiga", pontuacao=1000, acertos=8,
                finalizada_em=self.agora - timedelta(hours=2),
            )
            self.adicionar_partida(
                session, nome="Sem horário", pontuacao=1000, acertos=8,
                finalizada_em=None,
            ).finalizada_em = None
            self.adicionar_partida(
                session, nome="ID posterior", pontuacao=1000, acertos=8,
                finalizada_em=self.agora,
                partida_id=UUID(int=100),
            )
            self.adicionar_partida(
                session, nome="ID anterior", pontuacao=1000, acertos=8,
                finalizada_em=self.agora,
                partida_id=UUID(int=99),
            )
            session.commit()
        nomes = [item.jogador for item in self.listar()]
        self.assertEqual(nomes, [
            "Mais antiga",
            "Mais acertos",
            "ID anterior",
            "ID posterior",
            "Sem horário",
            "Menos acertos",
        ])

    def test_filtro_aceita_slug_e_uuid(self):
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Geral", pontuacao=1000, acertos=7,
            )
            self.adicionar_partida(
                session, nome="Tech", pontuacao=1200, acertos=8,
                categoria_id=self.tecnologia_id,
            )
            session.commit()
        self.assertEqual(
            [item.jogador for item in self.listar(categoria="geral")],
            ["Geral"],
        )
        self.assertEqual(
            [item.jogador for item in self.listar(categoria=str(self.tecnologia_id))],
            ["Tech"],
        )

    def test_exclui_categoria_privada_e_modo_nem_a_pato(self):
        with self.sessions() as session:
            self.adicionar_partida(
                session, nome="Privado", pontuacao=2000, acertos=10,
                categoria_id=self.privada_id,
            )
            self.adicionar_partida(
                session, nome="NP", pontuacao=1900, acertos=9,
                categoria_id=self.nem_pato_id,
            )
            self.adicionar_partida(
                session, nome="Inativo", pontuacao=1800, acertos=9,
                categoria_id=self.inativa_id,
            )
            self.adicionar_partida(
                session, nome="Público", pontuacao=900, acertos=6,
            )
            session.commit()
        self.assertEqual([item.jogador for item in self.listar()], ["Público"])

    def test_limite_padrao_e_limite_configuravel_sao_aplicados_no_sql(self):
        with self.sessions() as session:
            for indice in range(12):
                self.adicionar_partida(
                    session,
                    nome=f"Pessoa {indice}",
                    pontuacao=2000 - indice,
                    acertos=9,
                )
            session.commit()
        self.assertEqual(len(self.listar()), 10)
        self.assertEqual(len(self.listar(limit=12)), 12)

    def test_funcao_publica_aplica_limite_e_preserva_contrato(self):
        with self.sessions() as session:
            for indice in range(3):
                self.adicionar_partida(
                    session,
                    nome=f"Jogador {indice}",
                    pontuacao=1000 - indice,
                    acertos=8,
                )
            session.commit()

        with self.sessions() as session:
            corpo = ranking(categoria=None, limit=2, db=session)
        self.assertEqual(len(corpo), 2)
        self.assertEqual(corpo[0].posicao, 1)
        self.assertEqual(corpo[0].categoria.slug, "geral")
        self.assertNotIn("usuario_id", corpo[0].model_dump())

    def test_servico_rejeita_limites_invalidos(self):
        with self.sessions() as session:
            with self.assertRaisesRegex(ValueError, "entre 1 e 100"):
                self.servico.listar(session, limit=0)
            with self.assertRaisesRegex(ValueError, "entre 1 e 100"):
                self.servico.listar(session, limit=101)

    def test_openapi_declara_endpoint_publico_e_limites_http(self):
        operacao = app.openapi()["paths"]["/api/v1/ranking"]["get"]
        parametros = {item["name"]: item for item in operacao["parameters"]}
        self.assertNotIn("security", operacao)
        self.assertEqual(parametros["limit"]["schema"]["default"], 10)
        self.assertEqual(parametros["limit"]["schema"]["minimum"], 1)
        self.assertEqual(parametros["limit"]["schema"]["maximum"], 100)
        self.assertFalse(parametros["categoria"]["required"])


if __name__ == "__main__":
    unittest.main()
