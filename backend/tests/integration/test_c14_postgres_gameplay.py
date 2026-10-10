"""Aceitação PostgreSQL real da integração C1.4 com catálogos privados."""

import os
import unittest
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import MODO_NEM_A_PATO, MODO_QUIZ_CLASSICO, ORIGEM_USUARIO
from app.db.base import Base  # noqa: F401
from app.models import (
    Categoria,
    PartidaNemPato,
    Pergunta,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
    Usuario,
)
from app.services.partidas import PartidasPersistentes
from app.services.salas_nem_a_pato import SalasNemAPatoService


ENV_NAME = "C14_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} para PostgreSQL")
class TestC14PostgresGameplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(DATABASE_URL)
        esperado = os.getenv("C14_TEST_DATABASE_NAME", "").strip()
        if url.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} deve apontar para PostgreSQL")
        if (
            not url.database or "_test_" not in url.database
            or url.database == "quiz_estagio_db" or esperado != url.database
        ):
            raise RuntimeError("recusando banco não temporário explicitamente confirmado")
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with cls.engine.connect() as conexao:
            atual = conexao.scalar(text("SELECT current_database()"))
            revisao = conexao.scalar(text("SELECT version_num FROM alembic_version"))
        if atual != esperado or revisao != "0011":
            cls.engine.dispose()
            raise RuntimeError(f"banco/revisão inesperados: {atual!r}, {revisao!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.conexao = self.engine.connect()
        self.transacao = self.conexao.begin()
        self.sessions = sessionmaker(bind=self.conexao, expire_on_commit=False)
        with self.sessions() as db:
            self.usuario = Usuario(
                id=uuid4(), nome="C14 U1",
                email=f"c14-{uuid4()}@example.com", senha_hash="hash",
            )
            self.outro = Usuario(
                id=uuid4(), nome="C14 U2",
                email=f"c14-{uuid4()}@example.com", senha_hash="hash",
            )
            db.add_all((self.usuario, self.outro))
            db.flush()
            self.classic = Categoria(
                id=uuid4(), slug=f"c14-classic-{uuid4().hex[:8]}",
                nome="C14 Classic", modo=MODO_QUIZ_CLASSICO,
                origem=ORIGEM_USUARIO, usuario_id=self.usuario.id, ativa=True,
            )
            self.np = Categoria(
                id=uuid4(), slug=f"c14-np-{uuid4().hex[:8]}",
                nome="C14 NP", modo=MODO_NEM_A_PATO,
                origem=ORIGEM_USUARIO, usuario_id=self.usuario.id, ativa=True,
            )
            self.np_outro = Categoria(
                id=uuid4(), slug=f"c14-np-outro-{uuid4().hex[:8]}",
                nome="C14 NP Outro", modo=MODO_NEM_A_PATO,
                origem=ORIGEM_USUARIO, usuario_id=self.outro.id, ativa=True,
            )
            db.add_all((self.classic, self.np, self.np_outro))
            db.flush()
            inicio = (db.scalar(select(func.max(Pergunta.id))) or 0) + 1
            db.add_all(Pergunta(
                id=inicio + indice, categoria_id=self.classic.id,
                enunciado=f"C14 Classic {indice}", alternativa_a="A",
                alternativa_b="B", alternativa_c="C", alternativa_d="D",
                alternativa_correta=0, explicacao="C14",
                origem=ORIGEM_USUARIO, usuario_id=self.usuario.id,
            ) for indice in range(10))
            db.add_all(PerguntaNemPato(
                categoria_id=categoria.id, enunciado=f"C14 NP {owner.nome} {indice}",
                resposta_numerica=indice, explicacao="C14",
                origem=ORIGEM_USUARIO, usuario_id=owner.id,
            ) for owner, categoria in (
                (self.usuario, self.np), (self.outro, self.np_outro)
            ) for indice in range(10))
            db.commit()

    def tearDown(self):
        if self.transacao.is_active:
            self.transacao.rollback()
        self.conexao.close()

    def test_classic_uuid_privado_isola_owner_e_materializa_dez(self):
        with self.sessions() as db:
            criada = PartidasPersistentes().criar(
                db, None, str(self.classic.id), db.get(Usuario, self.usuario.id)
            )
            self.assertEqual(criada.categoria, f"privada:{self.classic.id}")
        with self.sessions() as db:
            ocorrencias = list(db.scalars(select(Pergunta).join(
                Pergunta.partidas_pergunta
            ).where(Pergunta.categoria_id == self.classic.id)))
            self.assertEqual(len(ocorrencias), 10)
            self.assertEqual({item.usuario_id for item in ocorrencias}, {self.usuario.id})
            with self.assertRaises(HTTPException) as erro:
                PartidasPersistentes().criar(
                    db, None, str(self.classic.id), db.get(Usuario, self.outro.id)
                )
            self.assertEqual(erro.exception.status_code, 422)

    def test_np_pool_e_partida_isolam_owner_e_snapshotam_catalogo(self):
        pools = []

        def selecionar(perguntas, quantidade):
            pools.append(list(perguntas))
            privadas = [
                pergunta for pergunta in perguntas
                if pergunta.usuario_id == self.usuario.id
            ]
            return privadas[:quantidade]

        servico = SalasNemAPatoService(
            selecionar_perguntas=selecionar,
            gerador_codigo=lambda: f"C14{uuid4().hex[:4]}".upper(),
            gerador_credencial=lambda: uuid4().hex,
        )
        with self.sessions() as db:
            host = servico.criar(db, "Host", db.get(Usuario, self.usuario.id))
        for nome in ("Dois", "Três"):
            with self.sessions() as db:
                servico.entrar(db, host.sala.codigo, nome)
        with self.sessions() as db:
            resultado = servico.iniciar(
                db, host.sala.codigo, host.credencial_participante
            )
            sala = db.scalar(select(SalaNemPato).where(
                SalaNemPato.codigo == host.sala.codigo
            ))
            partida = db.get(PartidaNemPato, resultado.partida.id)
            rodadas = list(db.scalars(select(RodadaNemPato).where(
                RodadaNemPato.partida_id == partida.id
            )))
        self.assertEqual(sala.catalogo_usuario_id, self.usuario.id)
        self.assertEqual(partida.catalogo_usuario_id, self.usuario.id)
        self.assertEqual(len(rodadas), 10)
        self.assertEqual(len({rodada.pergunta_id for rodada in rodadas}), 10)
        self.assertTrue(any(p.origem == "OFICIAL" for p in pools[0]))
        self.assertTrue(any(p.usuario_id == self.usuario.id for p in pools[0]))
        self.assertFalse(any(p.usuario_id == self.outro.id for p in pools[0]))


if __name__ == "__main__":
    unittest.main()
