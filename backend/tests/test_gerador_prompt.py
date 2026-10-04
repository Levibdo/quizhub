import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.cli import main as cli_main
from app.db.base import Base
from app.db.seed import seed_database
from app.conteudo import CATEGORIAS_OFICIAIS, MODO_QUIZ_CLASSICO
from app.models import Categoria, Partida, Pergunta, Resposta
from app.services.gerador_prompt import (
    DIFICULDADES,
    PUBLICO_PADRAO,
    QUANTIDADE_MAXIMA_PROMPT,
    ParametrosPrompt,
    ParametrosPromptInvalidos,
    gerar_prompt_perguntas,
)


class TestGeradorPrompt(unittest.TestCase):
    def parametros(self, **alteracoes):
        dados = {
            "categoria_id": "entretenimento",
            "tema": "Cinema, séries, música e cultura pop",
            "quantidade": 34,
            "dificuldade": "Mista",
            "publico_alvo": "Universitários",
        }
        dados.update(alteracoes)
        return ParametrosPrompt(**dados)

    def test_prompt_valido_obedece_ao_contrato_do_importador(self):
        prompt = gerar_prompt_perguntas(self.parametros())

        trechos = (
            '"modo": "quiz_classico"',
            '"categoria_id": "entretenimento"',
            "exatamente 34 perguntas",
            "exatamente 4 alternativas",
            '"alternativa_correta" deve ser um índice numérico 0, 1, 2 ou 3',
            "A explicação é obrigatória",
            "Retorne exclusivamente um objeto JSON válido",
            "Não inclua Markdown nem cercas de código como ```json",
            "Retorne somente o objeto JSON válido",
            "Cada pergunta deve ser independente das demais e compreensível "
            "sem depender de outra pergunta do conjunto.",
            "duplicações semânticas",
            "incorretas devem ser plausíveis",
            "Distribua a posição da alternativa correta",
        )
        for trecho in trechos:
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, prompt)

    def test_dificuldades_validas_sao_normalizadas(self):
        for dificuldade in DIFICULDADES:
            with self.subTest(dificuldade=dificuldade):
                prompt = gerar_prompt_perguntas(
                    self.parametros(dificuldade=dificuldade.lower())
                )
                self.assertIn(f"- dificuldade: {dificuldade}", prompt)

    def test_dificuldade_mista_orienta_distribuicao_equilibrada(self):
        orientacao = (
            "Quando a dificuldade for Mista, distribua as perguntas de forma "
            "aproximadamente equilibrada entre níveis fácil, médio e difícil."
        )
        prompt_misto = gerar_prompt_perguntas(
            self.parametros(dificuldade="Mista")
        )
        prompt_facil = gerar_prompt_perguntas(
            self.parametros(dificuldade="Fácil")
        )

        self.assertIn(orientacao, prompt_misto)
        self.assertNotIn(orientacao, prompt_facil)

    def test_publico_vazio_usa_padrao(self):
        prompt = gerar_prompt_perguntas(
            self.parametros(publico_alvo="   ")
        )
        self.assertIn(f"- público-alvo: {PUBLICO_PADRAO}", prompt)

    def test_quantidades_invalidas(self):
        casos = (
            (0, "maior que zero"),
            (-1, "maior que zero"),
            ("dez", "número inteiro"),
            (QUANTIDADE_MAXIMA_PROMPT + 1, "quantidade máxima"),
        )
        for quantidade, mensagem in casos:
            with self.subTest(quantidade=quantidade):
                with self.assertRaisesRegex(
                    ParametrosPromptInvalidos, mensagem
                ):
                    gerar_prompt_perguntas(
                        self.parametros(quantidade=quantidade)
                    )


class TestCliGeradorPrompt(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_database(session)

    def tearDown(self):
        self.engine.dispose()

    def executar(self, respostas):
        entradas = iter(respostas)
        saidas = []
        codigo = cli_main(
            ["prompt", "gerar"],
            input_fn=lambda _prompt: next(entradas),
            output=saidas.append,
            session_factory=self.sessions,
        )
        return codigo, saidas

    def snapshot(self):
        tabelas = (Categoria, Pergunta, Partida, Resposta)
        with self.sessions() as session:
            return {
                modelo.__tablename__: [
                    dict(row)
                    for row in session.execute(
                        select(modelo.__table__)
                    ).mappings()
                ]
                for modelo in tabelas
            }

    def test_fluxo_valido_mostra_categorias_e_delimita_prompt(self):
        antes = self.snapshot()
        codigo, saidas = self.executar(
            ("geral", "Conhecimentos gerais", "12", "2", "")
        )

        self.assertEqual(codigo, 0)
        self.assertTrue(any("Geral (geral)" in linha for linha in saidas))
        self.assertIn("----- PROMPT GERADO -----", saidas)
        self.assertIn("----- FIM DO PROMPT -----", saidas)
        prompt = saidas[saidas.index("----- PROMPT GERADO -----") + 1]
        self.assertIn('"categoria_id": "geral"', prompt)
        self.assertIn("exatamente 12 perguntas", prompt)
        self.assertIn("- dificuldade: Média", prompt)
        self.assertIn(f"- público-alvo: {PUBLICO_PADRAO}", prompt)
        self.assertEqual(self.snapshot(), antes)

    def test_categoria_inexistente_ou_inativa_e_rejeitada(self):
        codigo, saidas = self.executar(("inexistente",))
        self.assertEqual(codigo, 1)
        self.assertTrue(any("categoria ativa existente" in linha for linha in saidas))

        with self.sessions() as session:
            session.get(Categoria, CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["geral"]).ativa = False
            session.commit()
        codigo, saidas = self.executar(("geral",))
        self.assertEqual(codigo, 1)
        self.assertTrue(any("categoria ativa existente" in linha for linha in saidas))

    def test_quantidade_nao_numerica_e_rejeitada_sem_escrita(self):
        antes = self.snapshot()
        codigo, saidas = self.executar(
            ("geral", "Tema", "muitas")
        )
        self.assertEqual(codigo, 1)
        self.assertTrue(any("número inteiro" in linha for linha in saidas))
        self.assertEqual(self.snapshot(), antes)

    def test_quantidade_fora_do_intervalo_e_rejeitada(self):
        for quantidade in ("0", "-1", str(QUANTIDADE_MAXIMA_PROMPT + 1)):
            with self.subTest(quantidade=quantidade):
                codigo, saidas = self.executar(
                    ("geral", "Tema", quantidade, "Fácil", "Público")
                )
                self.assertEqual(codigo, 1)
                self.assertTrue(any("Erro:" in linha for linha in saidas))


if __name__ == "__main__":
    unittest.main()
