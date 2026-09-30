import unittest
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import MetaData, create_engine, event, select

from app.db.base import Base
from app.models import Categoria, Pergunta
from app.services.backfill_explicacoes import backfill_explicacoes


class TestBackfillExplicacoes(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        # Schema historico da 0006, anterior ao NOT NULL.
        metadata = MetaData()
        for tabela in Base.metadata.sorted_tables:
            tabela.to_metadata(metadata)
        metadata.tables["perguntas"].c.explicacao.nullable = True
        metadata.create_all(self.engine)
        self.linhas = [
            [categoria, f"Pergunta {i}?", f"Explicacao {categoria} {i}"]
            for categoria in ("geral", "matematica", "tecnologia")
            for i in range(35)
        ]
        with self.engine.begin() as conn:
            conn.execute(Categoria.__table__.insert(), [
                {"id": categoria, "nome": categoria}
                for categoria in ("geral", "matematica", "tecnologia")
            ])
            conn.execute(Pergunta.__table__.insert(), [
                dict(id=1000 + i * 3, categoria_id=cat, enunciado=enunciado,
                     alternativa_a="A", alternativa_b="B", alternativa_c="C",
                     alternativa_d="D", alternativa_correta=i % 4, ativa=bool(i % 2))
                for i, (cat, enunciado, _) in enumerate(self.linhas)
            ])

    def tearDown(self):
        self.engine.dispose()

    def xlsx(self, cabecalho=("categoria_id", "enunciado", "explicacao")):
        workbook = Workbook()
        workbook.active.append(cabecalho)
        # Ordem inversa e IDs nao sequenciais impedem correspondencia por posicao.
        for linha in reversed(self.linhas):
            workbook.active.append(linha)
        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        return stream.getvalue()

    def snapshot(self):
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(
                select(Pergunta.__table__).order_by(Pergunta.id)
            ).mappings()]

    def falha_sem_updates(self, regex, conteudo=None):
        antes = self.snapshot()
        updates = []

        def observar(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("UPDATE"):
                updates.append(statement)

        event.listen(self.engine, "before_cursor_execute", observar)
        try:
            with self.assertRaisesRegex(ValueError, regex):
                backfill_explicacoes(self.engine, conteudo or self.xlsx(), aplicar=True)
        finally:
            event.remove(self.engine, "before_cursor_execute", observar)
        self.assertEqual(updates, [])
        self.assertEqual(self.snapshot(), antes)

    def test_valido_105_correspondencias_sem_escrita(self):
        antes = self.snapshot()
        self.assertEqual(backfill_explicacoes(self.engine, self.xlsx()), 105)
        self.assertEqual(self.snapshot(), antes)

    def test_somente_explicacao_muda_e_repeticao_preserva_dados(self):
        antes = self.snapshot()
        self.assertEqual(backfill_explicacoes(self.engine, self.xlsx(), aplicar=True), 105)
        depois = self.snapshot()
        esperado = {(cat, enunciado): exp for cat, enunciado, exp in self.linhas}
        for original, atual in zip(antes, depois):
            self.assertEqual(atual.pop("explicacao"), esperado[(original["categoria_id"], original["enunciado"])])
            original.pop("explicacao")
            self.assertEqual(atual, original)
        completo = self.snapshot()
        self.assertEqual(backfill_explicacoes(self.engine, self.xlsx(), aplicar=True), 105)
        self.assertEqual(self.snapshot(), completo)

    def test_explicacao_vazia(self):
        self.linhas[0][2] = "  \t "
        self.falha_sem_updates("explicacao vazio")

    def test_categoria_vazia(self):
        self.linhas[0][0] = " "
        self.falha_sem_updates("categoria_id vazio")

    def test_enunciado_vazio(self):
        self.linhas[0][1] = " "
        self.falha_sem_updates("enunciado vazio")

    def test_categoria_invalida(self):
        self.linhas[0][0] = "outra"
        self.falha_sem_updates("categoria invalida")

    def test_coluna_explicacao_ausente(self):
        self.falha_sem_updates("Colunas obrigatorias", self.xlsx(("categoria_id", "enunciado", "outra")))

    def test_pergunta_xlsx_inexistente_no_banco(self):
        self.linhas[0][1] = "Inexistente"
        self.falha_sem_updates("Ausentes no banco: 1; ausentes no XLSX: 1")

    def test_pergunta_banco_ausente_no_xlsx(self):
        with self.engine.begin() as conn:
            conn.execute(Pergunta.__table__.insert().values(
                id=9999, categoria_id="geral", enunciado="Extra",
                alternativa_a="A", alternativa_b="B", alternativa_c="C",
                alternativa_d="D", alternativa_correta=0,
            ))
        self.falha_sem_updates("Ausentes no banco: 0; ausentes no XLSX: 1")

    def test_correspondencia_multipla(self):
        with self.engine.begin() as conn:
            conn.execute(Pergunta.__table__.update().where(Pergunta.id == 1003).values(enunciado="Pergunta 0?"))
        self.falha_sem_updates("Correspondencia multipla")

    def test_duplicata_xlsx(self):
        self.linhas[1] = self.linhas[0][:]
        self.falha_sem_updates("duplicata")

    def test_quantidade_diferente(self):
        self.linhas.pop()
        self.falha_sem_updates("Esperadas 105 linhas")

    def test_distribuicao_diferente(self):
        self.linhas[0][:2] = ["matematica", "Pergunta extra?"]
        self.falha_sem_updates("35/35/35")

    def test_identidade_exata_sem_strip(self):
        self.linhas[0][1] += " "
        self.falha_sem_updates("Ausentes no banco: 1")

    def test_rollback_integral_apos_updates(self):
        antes = self.snapshot()
        updates = []

        def falhar(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("UPDATE"):
                updates.append(statement)
                if len(updates) == 52:
                    raise RuntimeError("falha injetada")

        event.listen(self.engine, "before_cursor_execute", falhar)
        try:
            with self.assertRaisesRegex(RuntimeError, "falha injetada"):
                backfill_explicacoes(self.engine, self.xlsx(), aplicar=True)
        finally:
            event.remove(self.engine, "before_cursor_execute", falhar)
        self.assertEqual(len(updates), 52)
        self.assertEqual(self.snapshot(), antes)


if __name__ == "__main__":
    unittest.main()
