import os
import re
import threading
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.base import Base  # noqa: F401 - registra modelos antes dos exports
from app.models import OperacaoAdministrativa, Usuario
from app.services.idempotencia_administrativa import (
    executar_operacao_idempotente,
)


URL_ENV = "QUIZHUB_IDEMPOTENCIA_TEST_DATABASE_URL"
NAME_ENV = "QUIZHUB_IDEMPOTENCIA_TEST_DATABASE_NAME"
DATABASE_URL = os.getenv(URL_ENV, "").strip()
AUTHORIZED_DATABASE = os.getenv(NAME_ENV, "").strip()
AUTHORIZED_NAME = re.compile(r"^quizhub_idempotencia_test_[a-z0-9_]+$")
FORBIDDEN_DATABASES = {"quizhub_prod_db", "quiz_estagio_db", "quizhub_loadtest_db"}


@unittest.skipUnless(
    DATABASE_URL and AUTHORIZED_DATABASE,
    f"configure {URL_ENV} e {NAME_ENV} para banco descartável vazio",
)
class TestIdempotenciaAdminPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError("o teste de idempotência exige PostgreSQL")
        if (
            AUTHORIZED_DATABASE in FORBIDDEN_DATABASES
            or not AUTHORIZED_NAME.fullmatch(AUTHORIZED_DATABASE)
            or parsed.database != AUTHORIZED_DATABASE
        ):
            raise RuntimeError("banco descartável não passou pela proteção de nome")
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        cls.config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        with cls.engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != AUTHORIZED_DATABASE:
                raise RuntimeError("conexão aponta para banco não autorizado")
            tabelas = connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )).scalars().all()
            if tabelas:
                raise RuntimeError("o banco de idempotência deve começar vazio")
        cls._migrar("upgrade", "0018")
        cls.factory = sessionmaker(cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @classmethod
    def _migrar(cls, direcao, revisao):
        anterior = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = DATABASE_URL
        try:
            getattr(command, direcao)(cls.config, revisao)
        finally:
            if anterior is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = anterior

    @classmethod
    def _revisao(cls):
        with cls.engine.connect() as connection:
            return connection.scalar(text("SELECT version_num FROM alembic_version"))

    def setUp(self):
        if self._revisao() != "0019":
            return
        with self.factory.begin() as db:
            db.execute(text("DELETE FROM operacoes_administrativas"))
            db.execute(text("DELETE FROM usuarios"))
            self.admin_a = Usuario(
                nome="Admin PG A", email="admin-a@idempotencia.test",
                senha_hash="hash", perfil="ADMIN",
            )
            self.admin_b = Usuario(
                nome="Admin PG B", email="admin-b@idempotencia.test",
                senha_hash="hash", perfil="ADMIN",
            )
            db.add_all([self.admin_a, self.admin_b])
            db.flush()
            self.admin_a_id = self.admin_a.id
            self.admin_b_id = self.admin_b.id

    def _executar(self, admin_id, chave, executar, **kwargs):
        return executar_operacao_idempotente(
            self.factory,
            administrador_id=admin_id,
            tipo_operacao="ATIVAR_CATALOGO",
            recurso_tipo="CATALOGO_OFICIAL",
            recurso_id="quiz-v3",
            chave_idempotencia=chave,
            pedido={"versao": 3},
            executar=executar,
            **kwargs,
        )

    def test_01_upgrade_downgrade_e_reupgrade(self):
        self._migrar("upgrade", "0019")
        self.assertEqual(self._revisao(), "0019")
        inspetor = inspect(self.engine)
        self.assertIn("operacoes_administrativas", inspetor.get_table_names())
        unicos = {item["name"] for item in inspetor.get_unique_constraints(
            "operacoes_administrativas"
        )}
        self.assertIn("uq_operacoes_admin_escopo_chave", unicos)
        self._migrar("downgrade", "0018")
        self.assertEqual(self._revisao(), "0018")
        self.assertNotIn(
            "operacoes_administrativas", inspect(self.engine).get_table_names()
        )
        self._migrar("upgrade", "0019")
        self.assertEqual(self._revisao(), "0019")

    def test_02_concorrencia_permita_uma_execucao(self):
        iniciou = threading.Event()
        liberar = threading.Event()
        resultados = []

        def lenta(db):
            iniciou.set()
            self.assertTrue(liberar.wait(timeout=5))
            return 200, {"ok": True}

        def primeira():
            try:
                resultados.append(self._executar(self.admin_a_id, "concorrente", lenta))
            except Exception as erro:  # pragma: no cover - diagnóstico concorrente
                resultados.append(erro)

        thread = threading.Thread(target=primeira)
        thread.start()
        self.assertTrue(iniciou.wait(timeout=5))
        with self.assertRaises(HTTPException) as conflito:
            self._executar(
                self.admin_a_id, "concorrente", lambda db: (200, {"duplicada": True})
            )
        self.assertEqual(conflito.exception.status_code, 409)
        self.assertEqual(
            conflito.exception.detail["codigo"],
            "OPERACAO_ADMINISTRATIVA_EM_ANDAMENTO",
        )
        liberar.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(resultados), 1)
        self.assertNotIsInstance(resultados[0], Exception)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count(OperacaoAdministrativa.id))), 1
            )

    def test_03_falha_rollback_repeticao_e_separacao(self):
        with self.assertRaises(RuntimeError):
            self._executar(
                self.admin_a_id, "falha-pg",
                lambda db: (_ for _ in ()).throw(RuntimeError("falha artificial")),
            )
        recuperada = self._executar(
            self.admin_a_id, "falha-pg", lambda db: (200, {"ok": True}),
            permitir_recuperacao=True,
        )
        separada = self._executar(
            self.admin_b_id, "falha-pg", lambda db: (201, {"ok": True})
        )
        repetida = self._executar(
            self.admin_a_id, "falha-pg", lambda db: (500, {"nao": "executar"})
        )
        self.assertNotEqual(recuperada.operacao_id, separada.operacao_id)
        self.assertTrue(repetida.reproduzido)
        with self.factory() as db:
            registros = list(db.scalars(select(OperacaoAdministrativa)))
            self.assertEqual(len(registros), 2)
            self.assertEqual({item.estado for item in registros}, {"CONCLUIDA"})


if __name__ == "__main__":
    unittest.main()
