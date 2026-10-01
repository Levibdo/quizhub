import csv
import json
import tempfile
import unittest
from collections import Counter
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli import main as cli_main
from app.db.base import Base
from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app
from app.models import Pergunta
from app.services.importador_perguntas import (
    ArquivoImportacaoInvalido,
    COLUNAS_OBRIGATORIAS,
    ImportadorPerguntas,
    detectar_formato,
)
from tests.test_importador_perguntas import criar_xlsx


def linha(
    enunciado="Nova pergunta?",
    categoria="geral",
    alternativa=0,
    explicacao="Explicação válida.",
):
    return (
        categoria, enunciado, "A", "B", "C", "D", alternativa, explicacao
    )


def criar_csv(linhas, *, bom=False, cabecalho=COLUNAS_OBRIGATORIAS):
    arquivo = StringIO(newline="")
    escritor = csv.writer(arquivo, delimiter=",")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    conteudo = arquivo.getvalue().encode("utf-8")
    return (b"\xef\xbb\xbf" + conteudo) if bom else conteudo


def criar_json(perguntas, categoria="geral", modo="quiz_classico"):
    return json.dumps(
        {"modo": modo, "categoria_id": categoria, "perguntas": perguntas},
        ensure_ascii=False,
    ).encode("utf-8")


def pergunta_json(
    enunciado="Nova pergunta?",
    alternativas=None,
    alternativa=0,
    explicacao="Explicação válida.",
):
    return {
        "enunciado": enunciado,
        "alternativas": alternativas or ["A", "B", "C", "D"],
        "alternativa_correta": alternativa,
        "explicacao": explicacao,
    }


class TestCatalogosVersionados(unittest.TestCase):
    def test_contagens_atuais_dos_catalogos_recomendados(self):
        dados = Path(__file__).parents[1] / "dados"
        oficial = ImportadorPerguntas.ler(
            (dados / "perguntas_oficiais_com_explicacoes.xlsx").read_bytes(),
            "xlsx",
        )
        entretenimento = ImportadorPerguntas.ler(
            (dados / "perguntas_entretenimento.json").read_bytes(),
            "json",
        )

        self.assertEqual(len(oficial), 105)
        self.assertEqual(
            Counter(item.dados["categoria_id"] for item in oficial),
            {"geral": 35, "matematica": 35, "tecnologia": 35},
        )
        self.assertEqual(len(entretenimento), 34)
        self.assertEqual(
            Counter(item.dados["categoria_id"] for item in entretenimento),
            {"entretenimento": 34},
        )


class TestImportadorMultiformato(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_database(session)
        self.importador = ImportadorPerguntas()

    def tearDown(self):
        self.engine.dispose()

    def quantidade(self):
        with self.sessions() as session:
            return session.scalar(select(func.count()).select_from(Pergunta))

    def validar(self, conteudo, formato):
        with self.sessions() as session:
            return self.importador.validar_arquivo(session, conteudo, formato)

    def test_csv_utf8_bom_e_virgulas_entre_aspas(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                relatorio = self.validar(
                    criar_csv([
                        linha(
                            enunciado="Cinema, música e televisão?",
                            explicacao="Sim, contém vírgulas e acentos.",
                        )
                    ], bom=bom),
                    "csv",
                )
                self.assertEqual(
                    (relatorio.formato, relatorio.total, relatorio.validas),
                    ("csv", 1, 1),
                )

    def test_csv_cabecalho_alternativa_e_categoria_invalidos(self):
        with self.assertRaisesRegex(
            ArquivoImportacaoInvalido, "colunas obrigatórias ausentes"
        ):
            self.validar(criar_csv([], cabecalho=("enunciado",)), "csv")
        relatorio = self.validar(
            criar_csv([
                linha("Alternativa inválida", alternativa=4),
                linha("Categoria inválida", categoria="nao-existe"),
            ]),
            "csv",
        )
        self.assertEqual((relatorio.validas, relatorio.invalidas), (0, 2))
        self.assertIn("entre 0 e 3", relatorio.erros[0].motivo)
        self.assertEqual(relatorio.erros[1].motivo, "categoria inexistente")

    def test_csv_rejeita_codificacao_e_sintaxe_invalidas(self):
        with self.assertRaisesRegex(ArquivoImportacaoInvalido, "UTF-8"):
            self.validar(b"\xff\xfe", "csv")
        cabecalho = ",".join(COLUNAS_OBRIGATORIAS)
        with self.assertRaisesRegex(ArquivoImportacaoInvalido, "CSV inválido"):
            self.validar((cabecalho + '\n"campo sem fim').encode(), "csv")

    def test_json_contrato_valido_e_categoria_inexistente(self):
        valido = self.validar(criar_json([pergunta_json()]), "json")
        self.assertEqual((valido.total, valido.validas, valido.invalidas), (1, 1, 0))
        invalido = self.validar(
            criar_json([pergunta_json()], categoria="nao-existe"), "json"
        )
        self.assertEqual(invalido.invalidas, 1)
        self.assertEqual(invalido.erros[0].motivo, "categoria inexistente")

    def test_json_rejeita_documento_malformado_modo_e_lista_vazia(self):
        casos = (
            (b"{", "JSON malformado"),
            (criar_json([pergunta_json()], modo="outro"), "quiz_classico"),
            (criar_json([]), "lista não vazia"),
        )
        for conteudo, mensagem in casos:
            with self.subTest(mensagem=mensagem):
                with self.assertRaisesRegex(ArquivoImportacaoInvalido, mensagem):
                    self.validar(conteudo, "json")

    def test_json_valida_quatro_alternativas_indice_e_explicacao(self):
        relatorio = self.validar(criar_json([
            pergunta_json("Três?", alternativas=["A", "B", "C"]),
            pergunta_json("Índice?", alternativa=4),
            pergunta_json("Sem explicação?", explicacao="   "),
        ]), "json")
        self.assertEqual((relatorio.total, relatorio.validas, relatorio.invalidas), (3, 0, 3))
        self.assertIn("exatamente quatro", relatorio.erros[0].motivo)
        self.assertIn("entre 0 e 3", relatorio.erros[1].motivo)
        self.assertIn("explicacao", relatorio.erros[2].motivo)

    def test_duplicidade_json_e_validacao_repetida_nao_persistem(self):
        conteudo = criar_json([
            pergunta_json("Qual é a capital do Brasil?"),
            pergunta_json("Pergunta realmente nova"),
            pergunta_json("Pergunta realmente nova"),
            pergunta_json("Inválida", alternativa=9),
        ])
        antes = self.quantidade()
        primeira = self.validar(conteudo, "json")
        segunda = self.validar(conteudo, "json")
        self.assertEqual(primeira.model_dump(), segunda.model_dump())
        self.assertEqual(
            (primeira.total, primeira.validas, primeira.duplicadas, primeira.invalidas),
            (4, 1, 2, 1),
        )
        self.assertEqual(self.quantidade(), antes)

    def test_importacao_mista_preserva_existente_e_gera_ids_seguros(self):
        conteudo = criar_csv([
            linha("Qual é a capital do Brasil?", explicacao="Não sobrescrever"),
            linha("Nova com ID seguro"),
            linha("Inválida", alternativa=8),
        ])
        with self.sessions() as session:
            existente_antes = dict(session.execute(
                select(Pergunta.__table__).where(Pergunta.id == 1)
            ).mappings().one())
            resultado = self.importador.importar_arquivo(session, conteudo, "csv")
        self.assertEqual(
            (resultado.total, resultado.criadas, resultado.falhas), (3, 1, 2)
        )
        with self.sessions() as session:
            nova = session.scalar(
                select(Pergunta).where(Pergunta.enunciado == "Nova com ID seguro")
            )
            existente_depois = dict(session.execute(
                select(Pergunta.__table__).where(Pergunta.id == 1)
            ).mappings().one())
        self.assertEqual(nova.id, 16)
        self.assertEqual(existente_depois, existente_antes)

    def test_xlsx_csv_json_usam_mesma_validacao(self):
        dados = [linha("Mesma regra", alternativa=7)]
        formatos = {
            "xlsx": criar_xlsx(dados),
            "csv": criar_csv(dados),
            "json": criar_json([pergunta_json("Mesma regra", alternativa=7)]),
        }
        motivos = []
        for formato, conteudo in formatos.items():
            relatorio = self.validar(conteudo, formato)
            motivos.append(relatorio.erros[0].motivo)
        self.assertEqual(motivos, ["alternativa_correta deve estar entre 0 e 3"] * 3)

    def test_deteccao_de_extensao(self):
        self.assertEqual(detectar_formato("PERGUNTAS.XLSX"), "xlsx")
        self.assertEqual(detectar_formato("perguntas.csv"), "csv")
        self.assertEqual(detectar_formato("perguntas.json"), "json")
        with self.assertRaisesRegex(ArquivoImportacaoInvalido, "não suportada"):
            detectar_formato("perguntas.txt")


class TestCliPerguntas(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_database(session)
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()
        self.engine.dispose()

    def arquivo(self, nome, conteudo):
        caminho = Path(self.temp.name) / nome
        caminho.write_bytes(conteudo)
        return str(caminho)

    def executar(self, argumentos, respostas=()):
        entradas = iter(respostas)
        saidas = []
        codigo = cli_main(
            argumentos,
            input_fn=lambda _prompt: next(entradas),
            output=saidas.append,
            session_factory=self.sessions,
        )
        return codigo, saidas

    def quantidade(self):
        with self.sessions() as session:
            return session.scalar(select(func.count()).select_from(Pergunta))

    def test_validar_autodetecta_tres_formatos_e_nao_persiste(self):
        arquivos = (
            self.arquivo("perguntas.xlsx", criar_xlsx([linha("XLSX nova")])),
            self.arquivo("perguntas.csv", criar_csv([linha("CSV nova")])),
            self.arquivo("perguntas.json", criar_json([pergunta_json("JSON nova")])),
        )
        antes = self.quantidade()
        for caminho in arquivos:
            codigo, saidas = self.executar(["perguntas", "validar", caminho])
            self.assertEqual(codigo, 0)
            self.assertTrue(any("Válidas: 1" in texto for texto in saidas))
        self.assertEqual(self.quantidade(), antes)

    def test_importar_confirma_ou_cancela(self):
        caminho = self.arquivo("perguntas.csv", criar_csv([linha("CLI nova")]))
        antes = self.quantidade()
        cancelado, saidas = self.executar(
            ["perguntas", "importar", caminho], ("n",)
        )
        self.assertEqual(cancelado, 0)
        self.assertEqual(self.quantidade(), antes)
        self.assertTrue(any("cancelada" in texto for texto in saidas))
        importado, saidas = self.executar(
            ["perguntas", "importar", caminho], ("sim",)
        )
        self.assertEqual(importado, 0)
        self.assertEqual(self.quantidade(), antes + 1)
        self.assertTrue(any("1 criada" in texto for texto in saidas))

    def test_extensao_nao_suportada_tem_mensagem_e_nao_persiste(self):
        caminho = self.arquivo("perguntas.txt", b"conteudo")
        antes = self.quantidade()
        codigo, saidas = self.executar(["perguntas", "validar", caminho])
        self.assertEqual(codigo, 1)
        self.assertTrue(any("não suportada" in texto for texto in saidas))
        self.assertEqual(self.quantidade(), antes)


class TestApiImportacaoXlsx(unittest.TestCase):
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

        def banco_teste():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = banco_teste
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_endpoint_continua_exclusivo_para_xlsx(self):
        resposta = self.client.post(
            "/api/v1/perguntas/importar",
            files={
                "arquivo": (
                    "perguntas.xlsx",
                    criar_xlsx([linha("Importada pela API")]),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.json()["criadas"], 1)

        csv = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("perguntas.csv", criar_csv([linha()]), "text/csv")},
        )
        self.assertEqual(csv.status_code, 422, csv.text)
        self.assertEqual(csv.json()["detail"], "envie um arquivo XLSX")


if __name__ == "__main__":
    unittest.main()
