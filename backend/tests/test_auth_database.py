import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import UniqueConstraint, Uuid, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Usuario


class TestUsuarioMetadata(unittest.TestCase):
    def test_colunas_regras_e_relacionamentos(self):
        usuarios = Base.metadata.tables["usuarios"]
        jogadores = Base.metadata.tables["jogadores"]

        self.assertEqual([coluna.name for coluna in usuarios.primary_key], ["id"])
        for nome in (
            "id",
            "nome",
            "email",
            "senha_hash",
            "ativo",
            "criado_em",
            "atualizado_em",
        ):
            self.assertFalse(usuarios.c[nome].nullable)
        self.assertTrue(
            any(
                isinstance(regra, UniqueConstraint)
                and tuple(regra.columns.keys()) == ("email",)
                for regra in usuarios.constraints
            )
        )
        self.assertIsInstance(jogadores.c.usuario_id.type, Uuid)
        self.assertTrue(jogadores.c.usuario_id.nullable)
        self.assertEqual(
            {fk.target_fullname for fk in jogadores.c.usuario_id.foreign_keys},
            {"usuarios.id"},
        )
        self.assertIn("ix_jogadores_usuario_id", {i.name for i in jogadores.indexes})
        self.assertEqual(set(Usuario.__mapper__.relationships.keys()), {"jogadores"})

    def test_email_unico_e_exigido_pelo_banco(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                [
                    Usuario(nome="A", email="a@example.com", senha_hash="hash"),
                    Usuario(nome="B", email="a@example.com", senha_hash="hash"),
                ]
            )
            with self.assertRaises(IntegrityError):
                session.commit()
        engine.dispose()


class TestMigration0005(unittest.TestCase):
    def setUp(self):
        path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0005_usuarios_autenticacao.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0005", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)

    def test_revision_chain_e_upgrade(self):
        self.assertEqual(self.migration.revision, "0005")
        self.assertEqual(self.migration.down_revision, "0004")
        with (
            patch.object(self.migration.op, "create_table") as create_table,
            patch.object(self.migration.op, "add_column") as add_column,
            patch.object(self.migration.op, "create_foreign_key") as create_fk,
            patch.object(self.migration.op, "create_index") as create_index,
        ):
            self.migration.upgrade()

        create_table.assert_called_once()
        self.assertEqual(create_table.call_args.args[0], "usuarios")
        add_column.assert_called_once()
        create_fk.assert_called_once()
        create_index.assert_called_once_with(
            "ix_jogadores_usuario_id", "jogadores", ["usuario_id"]
        )

    def test_downgrade_remove_vinculo_antes_de_usuarios(self):
        eventos = []
        with (
            patch.object(
                self.migration.op,
                "drop_index",
                side_effect=lambda *args, **kwargs: eventos.append("index"),
            ),
            patch.object(
                self.migration.op,
                "drop_constraint",
                side_effect=lambda *args, **kwargs: eventos.append("fk"),
            ),
            patch.object(
                self.migration.op,
                "drop_column",
                side_effect=lambda *args, **kwargs: eventos.append("column"),
            ),
            patch.object(
                self.migration.op,
                "drop_table",
                side_effect=lambda *args, **kwargs: eventos.append("table"),
            ),
        ):
            self.migration.downgrade()
        self.assertEqual(eventos, ["index", "fk", "column", "table"])


if __name__ == "__main__":
    unittest.main()
