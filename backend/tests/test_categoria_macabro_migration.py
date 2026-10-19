import importlib.util
import unittest
from pathlib import Path
from uuid import UUID

from app.conteudo import CATEGORIAS_OFICIAIS, MODO_NEM_A_PATO


class TestCategoriaMacabroMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0016_categoria_oficial_macabro.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0016", path)
        assert spec is not None and spec.loader is not None
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    def test_revision_chain_and_stable_identifier(self):
        self.assertEqual(
            (self.migration.revision, self.migration.down_revision),
            ("0016", "0015"),
        )
        expected = UUID("c73ff198-c1de-5787-b796-c74d2df1b696")
        self.assertEqual(UUID(self.migration.MACABRO_ID), expected)
        self.assertEqual(
            CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["macabro"], expected
        )

    def test_downgrade_is_non_destructive_for_referenced_category(self):
        source = Path(self.migration.__file__).read_text(encoding="utf-8")
        self.assertIn("NOT EXISTS (SELECT 1 FROM perguntas_nem_pato", source)
        self.assertIn("NOT EXISTS (SELECT 1 FROM partidas_nem_pato", source)


if __name__ == "__main__":
    unittest.main()
