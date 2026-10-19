import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app.cli import main as cli_main
from app.services.validador_catalogos_oficiais import validar_catalogos


def fonte(indice=1):
    return {
        "titulo": f"Fonte institucional {indice}",
        "url": f"https://example.org/fontes/{indice}",
        "acessada_em": "2026-10-14",
    }


def catalogo_quiz():
    categorias = []
    for slug in ("geral", "tecnologia", "matematica", "entretenimento"):
        perguntas = []
        dificuldades = ["FACIL"] * 30 + ["MEDIA"] * 45 + ["DIFICIL"] * 25
        for indice, dificuldade in enumerate(dificuldades, start=1):
            perguntas.append({
                "id_editorial": f"qc-{slug}-{indice:03d}",
                "enunciado": (
                    f"{slug} registro{indice} chave{indice * 17} "
                    f"evento{indice * 31} documento{indice * 47}?"
                ),
                "dificuldade": dificuldade,
                "alternativas": [
                    f"Alternativa {letra} {slug} {indice}" for letra in "ABCD"
                ],
                "resposta_correta": indice % 4,
                "explicacao": f"Explicação editorial verificável {slug} {indice}.",
                "fontes": [fonte(indice)],
            })
        categorias.append({"slug": slug, "nome": slug.title(), "perguntas": perguntas})
    return {
        "schema_version": "quizhub.quiz_classico.v2",
        "catalogo_id": "quiz_classico_v2",
        "versao": 2,
        "modo": "QUIZ_CLASSICO",
        "categorias": categorias,
    }


def catalogo_nem_pato():
    perguntas = []
    for indice in range(1, 101):
        perguntas.append({
            "id_editorial": f"np-macabro-{indice:03d}",
            "enunciado": (
                f"macabro registro{indice} ocorrência{indice * 19} "
                f"arquivo{indice * 37} quantidade?"
            ),
            "resposta_numerica": indice,
            "unidade": "unidades",
            "explicacao": f"Contexto histórico documentado do registro {indice}.",
            "tema_editorial": "história macabra",
            "natureza_resposta": "EXATA",
            "qualificacao_estimativa": None,
            "fontes": [fonte(indice)],
        })
    return {
        "schema_version": "quizhub.nem_a_pato.macabro.v1",
        "catalogo_id": "nem_a_pato_macabro_v1",
        "versao": 1,
        "modo": "NEM_A_PATO",
        "categoria": {"slug": "macabro", "nome": "Macabro", "perguntas": perguntas},
    }


class TestValidadorCatalogosOficiais(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def escrever(self, nome, documento):
        caminho = self.raiz / nome
        caminho.write_text(
            json.dumps(documento, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return caminho

    def codigos(self, relatorio):
        return [item.codigo for item in relatorio.erros]

    def test_catalogos_validos_e_hash_reprodutivel(self):
        quiz = self.escrever("quiz.json", catalogo_quiz())
        nem_pato = self.escrever("nem.json", catalogo_nem_pato())
        primeiro = validar_catalogos(quiz=quiz, nem_pato=nem_pato)
        segundo = validar_catalogos(quiz=quiz, nem_pato=nem_pato)
        self.assertTrue(primeiro.valido, primeiro.erros)
        self.assertEqual(primeiro.hashes, segundo.hashes)
        self.assertEqual(
            primeiro.hashes[str(quiz)], hashlib.sha256(quiz.read_bytes()).hexdigest()
        )

    def test_json_malformado(self):
        caminho = self.raiz / "invalido.json"
        caminho.write_text("{", encoding="utf-8")
        self.assertIn("json_invalido", self.codigos(validar_catalogos(quiz=caminho)))

    def test_resposta_ausente_alternativas_duplicadas_e_dificuldade_invalida(self):
        casos = (
            (lambda pergunta: pergunta.pop("resposta_correta"), "contrato_invalido"),
            (lambda pergunta: pergunta.update(alternativas=["A", "A", "C", "D"]),
             "alternativas_invalidas"),
            (lambda pergunta: pergunta.update(dificuldade="EXTREMA"),
             "contrato_invalido"),
        )
        for mutacao, esperado in casos:
            with self.subTest(esperado=esperado):
                documento = catalogo_quiz()
                mutacao(documento["categorias"][0]["perguntas"][0])
                nome = f"{esperado}-{len(list(self.raiz.iterdir()))}.json"
                caminho = self.escrever(nome, documento)
                self.assertIn(esperado, self.codigos(validar_catalogos(quiz=caminho)))

    def test_operadores_e_sinais_sao_preservados_ao_comparar_alternativas(self):
        documento = catalogo_quiz()
        perguntas = documento["categorias"][1]["perguntas"]
        perguntas[0].update(
            id_editorial="TEC-073",
            alternativas=["a == b", "a.equals(b)", "a = b", "a.compareTo(b) == 0"],
        )
        perguntas = documento["categorias"][2]["perguntas"]
        perguntas[9].update(
            id_editorial="MAT-N010",
            alternativas=["-2/3", "2/3", "-3/2", "3/2"],
        )
        perguntas[45].update(
            id_editorial="MAT-N046",
            alternativas=["-3", "3", "-(-3)", "+3"],
        )
        relatorio = validar_catalogos(
            quiz=self.escrever("quiz-operadores.json", documento)
        )
        self.assertTrue(relatorio.valido, relatorio.erros)
        self.assertNotIn("alternativas_invalidas", self.codigos(relatorio))

    def test_contagem_id_e_enunciado_duplicados(self):
        documento = catalogo_quiz()
        perguntas = documento["categorias"][0]["perguntas"]
        perguntas.pop()
        perguntas[1]["id_editorial"] = perguntas[0]["id_editorial"]
        perguntas[1]["enunciado"] = "  " + perguntas[0]["enunciado"].upper() + "  "
        relatorio = validar_catalogos(quiz=self.escrever("quiz.json", documento))
        self.assertTrue({
            "contagem_incorreta", "distribuicao_incorreta",
            "id_editorial_duplicado", "enunciado_duplicado",
        }.issubset(set(self.codigos(relatorio))))

    def test_url_malformada_e_estimativa_sem_qualificacao(self):
        documento = catalogo_nem_pato()
        documento["categoria"]["perguntas"][0]["fontes"][0]["url"] = "arquivo-local"
        relatorio = validar_catalogos(
            nem_pato=self.escrever("nem-url.json", documento)
        )
        self.assertIn("contrato_invalido", self.codigos(relatorio))

        documento = catalogo_nem_pato()
        pergunta = documento["categoria"]["perguntas"][0]
        pergunta["natureza_resposta"] = "ESTIMATIVA"
        relatorio = validar_catalogos(
            nem_pato=self.escrever("nem-estimativa.json", documento)
        )
        self.assertIn("estimativa_sem_qualificacao", self.codigos(relatorio))

    def test_manifesto_pronto_confere_integridade(self):
        quiz = self.escrever("quiz_classico_v2.json", catalogo_quiz())
        nem_pato = self.escrever(
            "nem_a_pato_macabro_v1.json", catalogo_nem_pato()
        )
        manifesto = {
            "schema_version": "quizhub.catalogos.manifest.v1",
            "catalogos": [
                {
                    "catalogo_id": "quiz_classico_v2",
                    "arquivo": quiz.name,
                    "schema_version": "quizhub.quiz_classico.v2",
                    "sha256": hashlib.sha256(quiz.read_bytes()).hexdigest(),
                    "status": "PRONTO",
                },
                {
                    "catalogo_id": "nem_a_pato_macabro_v1",
                    "arquivo": nem_pato.name,
                    "schema_version": "quizhub.nem_a_pato.macabro.v1",
                    "sha256": hashlib.sha256(nem_pato.read_bytes()).hexdigest(),
                    "status": "PRONTO",
                },
            ],
        }
        caminho = self.escrever("manifest.json", manifesto)
        self.assertTrue(validar_catalogos(manifesto=caminho).valido)
        quiz.write_text("{}", encoding="utf-8")
        self.assertIn(
            "manifesto_hash_divergente",
            self.codigos(validar_catalogos(manifesto=caminho)),
        )

    def test_manifesto_pendente_do_repositorio_e_valido(self):
        caminho = Path(__file__).parents[1] / "dados_oficiais" / "manifest.json"
        self.assertTrue(validar_catalogos(manifesto=caminho).valido)

    def test_cli_dry_run_nao_abre_banco_e_retorna_status(self):
        caminho = self.escrever("quiz.json", catalogo_quiz())

        def proibido():
            raise AssertionError("dry-run não deve abrir sessão de banco")

        saidas = []
        codigo = cli_main(
            ["catalogo-oficial", "validar", "--quiz-classico", str(caminho)],
            output=saidas.append,
            session_factory=proibido,
        )
        self.assertEqual(codigo, 0)
        self.assertTrue(any(linha.startswith("SHA-256 ") for linha in saidas))
        self.assertIn("Resultado: 0 erro(s)", saidas[-1])

        invalido = copy.deepcopy(catalogo_quiz())
        invalido["categorias"][0]["perguntas"].pop()
        caminho = self.escrever("quiz-invalido.json", invalido)
        self.assertEqual(cli_main(
            ["catalogo-oficial", "validar", "--quiz-classico", str(caminho)],
            output=lambda _linha: None,
            session_factory=proibido,
        ), 1)


if __name__ == "__main__":
    unittest.main()
