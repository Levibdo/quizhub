import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Categoria, Jogador, Partida, Usuario
from app.security import usuario_atual


class RankingPessoalTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            self.usuario = Usuario(
                nome="Ana", email=f"ana-{uuid4()}@example.com", senha_hash="hash"
            )
            self.outro = Usuario(
                nome="Bia", email=f"bia-{uuid4()}@example.com", senha_hash="hash"
            )
            self.sem_categoria = Usuario(
                nome="Caio", email=f"caio-{uuid4()}@example.com", senha_hash="hash"
            )
            db.add_all((self.usuario, self.outro, self.sem_categoria))
            db.flush()
            self.categoria_a = self._categoria(
                db, UUID(int=101), "Astronomia", self.usuario
            )
            self.categoria_b = self._categoria(
                db, UUID(int=102), "Biologia", self.usuario
            )
            self.categoria_alheia = self._categoria(
                db, UUID(int=103), "Categoria alheia", self.outro
            )
            self.categoria_np = self._categoria(
                db, UUID(int=104), "Nem a Pato", self.usuario,
                modo="NEM_A_PATO",
            )
            self.categoria_oficial = Categoria(
                id=UUID(int=105), slug="geral", nome="Geral",
                modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=True,
            )
            db.add(self.categoria_oficial)
            db.commit()

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[usuario_atual] = lambda: self.usuario
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    @staticmethod
    def _categoria(db, identificador, nome, usuario, modo="QUIZ_CLASSICO"):
        categoria = Categoria(
            id=identificador,
            slug=f"categoria-{identificador.int}",
            nome=nome,
            modo=modo,
            origem="USUARIO",
            usuario_id=usuario.id,
            ativa=True,
        )
        db.add(categoria)
        return categoria

    def _partida(
        self,
        db,
        identificador,
        categoria,
        pontuacao,
        *,
        usuario=None,
        visitante=False,
        status="FINALIZADA",
        finalizada_em=None,
    ):
        jogador = Jogador(
            nome="Jogador de teste",
            usuario_id=usuario.id if usuario else None,
            visitante_id=uuid4() if visitante else None,
        )
        db.add(jogador)
        db.flush()
        partida = Partida(
            id=identificador,
            jogador_id=jogador.id,
            categoria_id=categoria.id,
            status=status,
            pontuacao=pontuacao,
            acertos=0,
            erros=0,
            iniciada_em=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc),
            finalizada_em=finalizada_em,
        )
        db.add(partida)
        return partida

    def test_isola_propriedade_estado_origem_e_modo_com_desempate_estavel(self):
        cedo = datetime(2026, 11, 10, 10, 5, tzinfo=timezone.utc)
        tarde = cedo + timedelta(minutes=1)
        with self.sessions() as db:
            self._partida(
                db, UUID(int=1), self.categoria_a, 900,
                usuario=self.usuario, finalizada_em=cedo,
            )
            self._partida(
                db, UUID(int=3), self.categoria_a, 1200,
                usuario=self.usuario, finalizada_em=tarde,
            )
            self._partida(
                db, UUID(int=2), self.categoria_a, 1200,
                usuario=self.usuario, finalizada_em=cedo,
            )
            self._partida(
                db, UUID(int=4), self.categoria_a, 9999,
                usuario=self.outro, finalizada_em=cedo,
            )
            self._partida(
                db, UUID(int=5), self.categoria_a, 9998,
                visitante=True, finalizada_em=cedo,
            )
            self._partida(
                db, UUID(int=6), self.categoria_a, 9997,
                usuario=self.usuario, status="EM_ANDAMENTO",
            )
            self._partida(
                db, UUID(int=7), self.categoria_alheia, 9996,
                usuario=self.usuario, finalizada_em=cedo,
            )
            self._partida(
                db, UUID(int=8), self.categoria_oficial, 9995,
                usuario=self.usuario, finalizada_em=cedo,
            )
            self._partida(
                db, UUID(int=9), self.categoria_np, 9994,
                usuario=self.usuario, finalizada_em=cedo,
            )
            db.commit()

        resposta = self.client.get("/api/v1/meu-conteudo/ranking")
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(
            [item["categoria_nome"] for item in corpo],
            ["Astronomia", "Biologia"],
        )
        self.assertEqual(corpo[1]["partidas"], [])
        self.assertEqual(
            [(item["posicao"], item["partida_id"], item["pontuacao"])
             for item in corpo[0]["partidas"]],
            [(1, str(UUID(int=2)), 1200), (2, str(UUID(int=3)), 1200),
             (3, str(UUID(int=1)), 900)],
        )

    def test_estado_vazio_e_get_nao_altera_banco(self):
        with self.sessions() as db:
            antes = (
                db.scalar(select(func.count()).select_from(Partida)),
                db.scalar(select(func.count()).select_from(Jogador)),
            )
        resposta = self.client.get("/api/v1/meu-conteudo/ranking")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(resposta.json()), 2)
        self.assertTrue(all(not item["partidas"] for item in resposta.json()))
        with self.sessions() as db:
            depois = (
                db.scalar(select(func.count()).select_from(Partida)),
                db.scalar(select(func.count()).select_from(Jogador)),
            )
        self.assertEqual(antes, depois)

    def test_usuario_sem_categoria_recebe_lista_vazia(self):
        app.dependency_overrides[usuario_atual] = lambda: self.sem_categoria
        resposta = self.client.get("/api/v1/meu-conteudo/ranking")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), [])

    def test_anonimo_recebe_401(self):
        app.dependency_overrides.pop(usuario_atual)
        resposta = self.client.get("/api/v1/meu-conteudo/ranking")
        self.assertEqual(resposta.status_code, 401)


if __name__ == "__main__":
    unittest.main()
