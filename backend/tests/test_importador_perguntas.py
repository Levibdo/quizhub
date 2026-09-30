import unittest
from io import BytesIO
from unittest.mock import patch

from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed import seed_database
from app.models import Categoria, Pergunta
from app.services.importador_perguntas import (
    COLUNAS_OBRIGATORIAS,
    ArquivoImportacaoInvalido,
    ImportadorPerguntas,
)


def criar_xlsx(linhas, cabecalho=COLUNAS_OBRIGATORIAS):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(list(cabecalho))
    for linha in linhas:
        worksheet.append(list(linha))
    arquivo = BytesIO()
    workbook.save(arquivo)
    workbook.close()
    return arquivo.getvalue()


class TestImportadorPerguntas(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        seed_database(self.session)
        self.importador = ImportadorPerguntas()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def importar(self, linhas, cabecalho=COLUNAS_OBRIGATORIAS):
        return self.importador.importar(
            self.session,
            criar_xlsx(linhas, cabecalho),
        )

    def test_importacao_valida(self):
        relatorio = self.importar(
            [("tecnologia", "Nova?", "A", "B", "C", "D", 2, "  Explicacao de teste  ")]
        )
        self.assertEqual(relatorio.model_dump(), {
            "total": 1,
            "criadas": 1,
            "falhas": 0,
            "erros": [],
        })
        pergunta = self.session.scalar(
            select(Pergunta).where(Pergunta.enunciado == "Nova?")
        )
        self.assertEqual(pergunta.id, 16)
        self.assertEqual(pergunta.alternativa_correta, 2)
        self.assertEqual(pergunta.explicacao, "Explicacao de teste")

    def test_pergunta_ja_existente_nao_e_criada_novamente(self):
        tabela = Pergunta.__table__
        antes = self.session.execute(select(tabela).where(tabela.c.id == 1)).mappings().one()
        relatorio = self.importar(
            [("geral", "Qual é a capital do Brasil?", "X", "Y", "Z", "W", 1, "  Explicacao de teste  ")]
        )

        self.assertEqual((relatorio.total, relatorio.criadas, relatorio.falhas), (1, 0, 1))
        self.assertEqual(relatorio.erros[0].linha, 2)
        self.assertIn("pergunta duplicada", relatorio.erros[0].motivo)
        quantidade = self.session.scalar(select(func.count()).select_from(Pergunta))
        self.assertEqual(quantidade, 15)
        depois = self.session.execute(select(tabela).where(tabela.c.id == 1)).mappings().one()
        self.assertEqual(dict(antes), dict(depois))

    def test_explicacao_vazia_ou_apenas_espacos(self):
        for explicacao in (None, "", " \t\n "):
            with self.subTest(explicacao=explicacao):
                relatorio = self.importar([
                    ("geral", "Nova?", "A", "B", "C", "D", 0, explicacao)
                ])
                self.assertEqual((relatorio.criadas, relatorio.falhas), (0, 1))
                self.assertIn("explicacao", relatorio.erros[0].motivo)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Pergunta)), 15)

    def test_coluna_explicacao_ausente(self):
        with self.assertRaises(ArquivoImportacaoInvalido) as erro:
            self.importar(
                [("geral", "Nova?", "A", "B", "C", "D", 0)],
                cabecalho=COLUNAS_OBRIGATORIAS[:-1],
            )
        self.assertIn("explicacao", str(erro.exception))

    def test_duplicata_na_mesma_planilha_e_criada_uma_vez(self):
        linha = ("tecnologia", "Pergunta repetida?", "A", "B", "C", "D", 2, "  Explicacao de teste  ")
        relatorio = self.importar([linha, linha])

        self.assertEqual((relatorio.total, relatorio.criadas, relatorio.falhas), (2, 1, 1))
        self.assertEqual(relatorio.erros[0].linha, 3)
        self.assertIn("pergunta duplicada", relatorio.erros[0].motivo)
        quantidade = self.session.scalar(
            select(func.count())
            .select_from(Pergunta)
            .where(Pergunta.enunciado == "Pergunta repetida?")
        )
        self.assertEqual(quantidade, 1)

    def test_reimportar_mesma_planilha_nao_aumenta_quantidade(self):
        linhas = [
            ("geral", "Nova geral?", "A", "B", "C", "D", 0, "  Explicacao de teste  "),
            ("matematica", "Nova matematica?", "1", "2", "3", "4", 1, "  Explicacao de teste  "),
        ]
        primeira = self.importar(linhas)
        segunda = self.importar(linhas)

        self.assertEqual((primeira.criadas, primeira.falhas), (2, 0))
        self.assertEqual((segunda.criadas, segunda.falhas), (0, 2))
        self.assertTrue(
            all("pergunta duplicada" in erro.motivo for erro in segunda.erros)
        )
        quantidade = self.session.scalar(select(func.count()).select_from(Pergunta))
        self.assertEqual(quantidade, 17)

    def test_comparacao_remove_espacos_mas_preserva_caixa(self):
        primeira = self.importar(
            [(" geral ", "  Mesma pergunta?  ", "A", "B", "C", "D", 0, "  Explicacao de teste  ")]
        )
        duplicada = self.importar(
            [("geral", "Mesma pergunta?", "A", "B", "C", "D", 0, "  Explicacao de teste  ")]
        )
        caixa_diferente = self.importar(
            [("geral", "mesma pergunta?", "A", "B", "C", "D", 0, "  Explicacao de teste  ")]
        )

        self.assertEqual(primeira.criadas, 1)
        self.assertEqual((duplicada.criadas, duplicada.falhas), (0, 1))
        self.assertEqual(caixa_diferente.criadas, 1)

    def test_categoria_inexistente(self):
        relatorio = self.importar(
            [("nao-existe", "Nova?", "A", "B", "C", "D", 0, "  Explicacao de teste  ")]
        )
        self.assertEqual((relatorio.criadas, relatorio.falhas), (0, 1))
        self.assertEqual(relatorio.erros[0].motivo, "categoria inexistente")

    def test_categoria_inativa(self):
        self.session.get(Categoria, "tecnologia").ativa = False
        self.session.commit()
        relatorio = self.importar(
            [("tecnologia", "Nova?", "A", "B", "C", "D", 0, "  Explicacao de teste  ")]
        )
        self.assertEqual((relatorio.criadas, relatorio.falhas), (0, 1))
        self.assertEqual(relatorio.erros[0].motivo, "categoria inativa")

    def test_alternativa_correta_invalida(self):
        for alternativa in (-1, 4, "A", 1.5):
            with self.subTest(alternativa=alternativa):
                relatorio = self.importar(
                    [("geral", "Nova?", "A", "B", "C", "D", alternativa, "  Explicacao de teste  ")]
                )
                self.assertEqual((relatorio.criadas, relatorio.falhas), (0, 1))
                self.assertIn("entre 0 e 3", relatorio.erros[0].motivo)

    def test_campo_obrigatorio_vazio(self):
        relatorio = self.importar(
            [("geral", None, "A", "B", "C", "D", 0, "  Explicacao de teste  ")]
        )
        self.assertEqual((relatorio.criadas, relatorio.falhas), (0, 1))
        self.assertEqual(
            relatorio.erros[0].motivo,
            "campo obrigatório vazio: enunciado",
        )

    def test_importacao_parcial(self):
        relatorio = self.importar(
            [
                ("geral", "Válida 1", "A", "B", "C", "D", 0, "  Explicacao de teste  "),
                ("inexistente", "Inválida", "A", "B", "C", "D", 1, "  Explicacao de teste  "),
                ("matematica", "Válida 2", "10", "20", "30", "40", 3, "Explicacao de teste"),
            ]
        )
        self.assertEqual((relatorio.total, relatorio.criadas, relatorio.falhas), (3, 2, 1))
        self.assertEqual(relatorio.erros[0].linha, 3)
        quantidade = self.session.scalar(select(func.count()).select_from(Pergunta))
        self.assertEqual(quantidade, 17)

    def test_arquivo_sem_colunas_obrigatorias(self):
        with self.assertRaises(ArquivoImportacaoInvalido) as error:
            self.importar([], cabecalho=("categoria_id", "enunciado"))
        self.assertIn("colunas obrigatórias ausentes", str(error.exception))

    def test_erro_inesperado_desfaz_toda_importacao(self):
        conteudo = criar_xlsx(
            [("geral", "Não deve persistir", "A", "B", "C", "D", 0, "  Explicacao de teste  ")]
        )
        with patch.object(
            self.session,
            "flush",
            side_effect=RuntimeError("falha inesperada"),
        ):
            with self.assertRaisesRegex(RuntimeError, "falha inesperada"):
                self.importador.importar(self.session, conteudo)

        quantidade = self.session.scalar(select(func.count()).select_from(Pergunta))
        self.assertEqual(quantidade, 15)


if __name__ == "__main__":
    unittest.main()
