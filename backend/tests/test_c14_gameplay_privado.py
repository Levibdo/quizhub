import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.conteudo import (
    CATEGORIAS_OFICIAIS,
    MODO_QUIZ_CLASSICO,
    ORIGEM_USUARIO,
)
from app.db.base import Base
from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app
from app.models import Categoria, Partida, PartidaPergunta, Pergunta, Usuario
from app.security import usuario_atual_opcional
from app.services.partidas import PartidasPersistentes


class TestC14GameplayPrivado(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_database(session)
            self.usuario = Usuario(
                nome="Dona", email="dona-c14@example.com", senha_hash="hash"
            )
            self.outro = Usuario(
                nome="Outro", email="outro-c14@example.com", senha_hash="hash"
            )
            session.add_all((self.usuario, self.outro))
            session.flush()
            self.usuario_id = self.usuario.id
            self.outro_id = self.outro.id
            self.categoria = Categoria(
                id=uuid4(), slug="privada-c14", nome="Geral",
                modo=MODO_QUIZ_CLASSICO, origem=ORIGEM_USUARIO,
                usuario_id=self.usuario_id, ativa=True,
            )
            self.categoria_outro = Categoria(
                id=uuid4(), slug="privada-outro-c14", nome="Geral",
                modo=MODO_QUIZ_CLASSICO, origem=ORIGEM_USUARIO,
                usuario_id=self.outro_id, ativa=True,
            )
            session.add_all((self.categoria, self.categoria_outro))
            session.flush()
            for indice in range(12):
                session.add(Pergunta(
                    id=5000 + indice,
                    categoria_id=self.categoria.id,
                    enunciado=f"Privada C1.4 {indice}",
                    alternativa_a="A", alternativa_b="B",
                    alternativa_c="C", alternativa_d="D",
                    alternativa_correta=indice % 4,
                    explicacao=f"Explicação privada {indice}",
                    origem=ORIGEM_USUARIO, usuario_id=self.usuario_id,
                    ativa=indice not in (10, 11),
                    excluida_em=(
                        datetime(2026, 10, 10, tzinfo=timezone.utc)
                        if indice == 11 else None
                    ),
                ))
            for indice in range(10):
                session.add(Pergunta(
                    id=5100 + indice,
                    categoria_id=self.categoria_outro.id,
                    enunciado=f"Alheia {indice}",
                    alternativa_a="A", alternativa_b="B",
                    alternativa_c="C", alternativa_d="D",
                    alternativa_correta=0, explicacao="Alheia",
                    origem=ORIGEM_USUARIO, usuario_id=self.outro_id,
                ))
            session.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _usuario(self, session, usuario_id=None):
        return session.get(Usuario, usuario_id or self.usuario_id)

    def _ocorrencias(self, session, partida_id):
        return list(session.scalars(
            select(PartidaPergunta)
            .where(PartidaPergunta.partida_id == UUID(partida_id))
            .order_by(PartidaPergunta.ordem)
        ))

    def test_categorias_jogaveis_isolam_usuario_e_endpoint_publico(self):
        def banco_teste():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = banco_teste
        with TestClient(app) as client:
            publico = client.get("/api/v1/categorias").json()
            convidado = client.get("/api/v1/categorias/jogaveis").json()
            self.assertTrue(all(item["origem"] == "OFICIAL" for item in publico))
            self.assertEqual(publico, convidado)

            app.dependency_overrides[usuario_atual_opcional] = lambda: self.usuario
            autenticado = client.get("/api/v1/categorias/jogaveis")
            self.assertEqual(autenticado.status_code, 200, autenticado.text)
            ids = {item["id"] for item in autenticado.json()}
            self.assertIn(str(self.categoria.id), ids)
            self.assertNotIn(str(self.categoria_outro.id), ids)
            privada = next(
                item for item in autenticado.json()
                if item["id"] == str(self.categoria.id)
            )
            self.assertEqual(privada["origem"], "USUARIO")

    def test_classic_autoriza_uuid_exato_e_mantem_snapshots(self):
        servico = PartidasPersistentes()
        with self.sessions() as session:
            usuario = self._usuario(session)
            criada = servico.criar(
                session, None, str(self.categoria.id), usuario
            )
            ocorrencias = self._ocorrencias(session, criada.partida_id)
            self.assertEqual(criada.categoria, f"privada:{self.categoria.id}")
            self.assertEqual(len(ocorrencias), 10)
            self.assertEqual(len({item.pergunta_id for item in ocorrencias}), 10)
            self.assertTrue(all(
                item.pergunta.categoria_id == self.categoria.id
                and item.pergunta.origem == ORIGEM_USUARIO
                and item.pergunta.usuario_id == self.usuario_id
                and item.pergunta.ativa
                and item.pergunta.excluida_em is None
                for item in ocorrencias
            ))
            primeira = ocorrencias[0]
            snapshot = (
                primeira.enunciado_snapshot,
                primeira.alternativa_correta_snapshot,
                primeira.explicacao_snapshot,
            )
            primeira.pergunta.enunciado = "Alterada depois do início"
            primeira.pergunta.alternativa_correta = 3
            primeira.pergunta.explicacao = "Alterada"
            primeira.pergunta.ativa = False
            primeira.pergunta.excluida_em = datetime.now(timezone.utc)
            session.commit()
            session.refresh(primeira)
            self.assertEqual(snapshot, (
                primeira.enunciado_snapshot,
                primeira.alternativa_correta_snapshot,
                primeira.explicacao_snapshot,
            ))

    def test_classic_bloqueia_guest_outro_owner_e_slug_privado(self):
        servico = PartidasPersistentes()
        casos = (
            (None, str(self.categoria.id)),
            (self.outro_id, str(self.categoria.id)),
            (self.usuario_id, self.categoria.slug),
        )
        for usuario_id, identificador in casos:
            with self.subTest(usuario_id=usuario_id, identificador=identificador):
                with self.sessions() as session:
                    usuario = self._usuario(session, usuario_id) if usuario_id else None
                    with self.assertRaises(HTTPException) as erro:
                        servico.criar(session, "Guest", identificador, usuario)
                    self.assertEqual(erro.exception.status_code, 422)

    def test_classic_insuficiente_rejeita_sem_partida_parcial(self):
        with self.sessions() as session:
            uma = session.scalar(select(Pergunta).where(
                Pergunta.categoria_id == self.categoria.id,
                Pergunta.ativa.is_(True),
                Pergunta.excluida_em.is_(None),
            ))
            uma.ativa = False
            session.commit()
            antes = session.scalar(select(func.count()).select_from(Partida))
            with self.assertRaises(HTTPException) as erro:
                PartidasPersistentes().criar(
                    session, None, str(self.categoria.id), self._usuario(session)
                )
            self.assertEqual(erro.exception.status_code, 422)
            depois = session.scalar(select(func.count()).select_from(Partida))
            self.assertEqual(antes, depois)

    def test_classic_oficial_por_uuid_e_slug_legado_permanece_oficial(self):
        geral_id = CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["geral"]
        with self.sessions() as session:
            proximo = 5200
            existentes = session.scalar(select(func.count()).select_from(Pergunta).where(
                Pergunta.categoria_id == geral_id
            ))
            for indice in range(10 - existentes):
                session.add(Pergunta(
                    id=proximo + indice, categoria_id=geral_id,
                    enunciado=f"Oficial extra {indice}",
                    alternativa_a="A", alternativa_b="B",
                    alternativa_c="C", alternativa_d="D",
                    alternativa_correta=0, explicacao="Oficial",
                ))
            session.commit()
        for identificador in (str(geral_id), "geral"):
            with self.subTest(identificador=identificador), self.sessions() as session:
                criada = PartidasPersistentes().criar(
                    session, None, identificador, self._usuario(session)
                )
                self.assertEqual(criada.categoria, "geral")
                self.assertTrue(all(
                    item.pergunta.origem == "OFICIAL"
                    for item in self._ocorrencias(session, criada.partida_id)
                ))


if __name__ == "__main__":
    unittest.main()
