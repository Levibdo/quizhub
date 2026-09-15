import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from app.data.perguntas import PERGUNTAS
from app.schemas.partidas import CriarPartida, EnviarResposta
from app.services.partidas import PartidasEmMemoria


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


class TestPartidas(unittest.TestCase):
    def setUp(self):
        self.relogio = Relogio()
        self.servico = PartidasEmMemoria(self.relogio)
        self.criada = self.servico.criar("Levi", "tecnologia")

    def pergunta(self):
        return self.servico.partidas[self.criada.partida_id].perguntas[
            self.servico.partidas[self.criada.partida_id].indice
        ]

    def responder(self, alternativa):
        return self.servico.responder(self.criada.partida_id, self.pergunta().id, alternativa)

    def test_criacao_valida_e_sem_gabarito(self):
        partida = self.servico.partidas[self.criada.partida_id]
        self.assertEqual(self.criada.status, "EM_ANDAMENTO")
        self.assertEqual((self.criada.pontuacao, self.criada.acertos, self.criada.erros), (0, 0, 0))
        self.assertEqual(len({p.id for p in partida.perguntas}), 3)
        self.assertTrue(all(p.categoria == "tecnologia" for p in partida.perguntas))
        self.assertIsNotNone(self.criada.iniciada_em)
        self.assertIsNotNone(self.criada.pergunta_disponibilizada_em)
        self.assertNotIn("correta", self.criada.model_dump()["pergunta_atual"])

    def test_categoria_inexistente(self):
        with self.assertRaises(HTTPException) as erro:
            self.servico.criar("Levi", "inexistente")
        self.assertEqual(erro.exception.status_code, 422)

    def test_jogador_vazio(self):
        with self.assertRaises(ValidationError):
            CriarPartida(jogador="   ", categoria="tecnologia")

    def test_resposta_correta(self):
        self.relogio.agora = 2
        resposta = self.responder(self.pergunta().correta)
        self.assertIs(resposta.correta, True)
        self.assertFalse(resposta.timeout)
        self.assertEqual((resposta.pontos_ganhos, resposta.pontuacao, resposta.acertos, resposta.erros), (230, 230, 1, 0))
        self.assertIn("pontos_ganhos", resposta.model_dump())
        self.assertNotIn("pontos", resposta.model_dump())
        self.assertNotIn("correta", resposta.model_dump()["pergunta_atual"])

    def test_limites_da_pontuacao(self):
        for decorrido, pontos_esperados, timeout_esperado in (
            (0.0, 250, False),
            (0.2, 250, False),
            (1.2, 240, False),
            (14.2, 110, False),
            (15.0, 0, True),
        ):
            with self.subTest(decorrido=decorrido):
                relogio = Relogio()
                servico = PartidasEmMemoria(relogio)
                criada = servico.criar("Levi", "tecnologia")
                pergunta = servico.partidas[criada.partida_id].perguntas[0]
                relogio.agora = decorrido
                resposta = servico.responder(criada.partida_id, pergunta.id, pergunta.correta)
                self.assertEqual(resposta.pontos_ganhos, pontos_esperados)
                self.assertEqual(resposta.timeout, timeout_esperado)

    def test_resposta_errada(self):
        resposta = self.responder((self.pergunta().correta + 1) % 4)
        self.assertEqual((resposta.pontos_ganhos, resposta.pontuacao, resposta.acertos, resposta.erros), (0, 0, 0, 1))
        self.assertIs(resposta.correta, False)
        self.assertFalse(resposta.timeout)

    def test_pergunta_diferente_e_repetida(self):
        antiga = self.pergunta().id
        with self.assertRaises(HTTPException) as erro:
            self.servico.responder(self.criada.partida_id, -1, 0)
        self.assertEqual(erro.exception.status_code, 409)
        self.responder(0)
        with self.assertRaises(HTTPException) as erro:
            self.servico.responder(self.criada.partida_id, antiga, 0)
        self.assertEqual(erro.exception.status_code, 409)

    def test_alternativa_fora_do_intervalo(self):
        with self.assertRaises(HTTPException) as erro:
            self.responder(4)
        self.assertEqual(erro.exception.status_code, 422)
        with self.assertRaises(ValidationError):
            EnviarResposta(pergunta_id=1, alternativa=-1)

    def test_partida_inexistente(self):
        with self.assertRaises(HTTPException) as erro:
            self.servico.responder("desconhecida", 1, 0)
        self.assertEqual(erro.exception.status_code, 404)

    def test_finalizacao_e_resposta_posterior(self):
        ids = []
        for _ in range(3):
            ids.append(self.pergunta().id)
            resposta = self.responder(self.pergunta().correta)
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(resposta.status, "FINALIZADA")
        self.assertEqual((resposta.acertos, resposta.erros), (3, 0))
        self.assertIsNone(resposta.pergunta_atual)
        self.assertIsNotNone(resposta.finalizada_em)
        with self.assertRaises(HTTPException) as erro:
            self.servico.responder(self.criada.partida_id, ids[-1], 0)
        self.assertEqual(erro.exception.status_code, 409)

    def test_timeout_no_limite_ignora_alternativa_correta(self):
        self.relogio.agora = 15
        resposta = self.responder(self.pergunta().correta)
        self.assertTrue(resposta.timeout)
        self.assertIsNone(resposta.correta)
        self.assertEqual((resposta.pontos_ganhos, resposta.acertos, resposta.erros), (0, 0, 1))
        self.assertIn("pontos_ganhos", resposta.model_dump())
        self.assertNotIn("pontos", resposta.model_dump())

    def test_relogio_reinicia_na_proxima_pergunta(self):
        self.relogio.agora = 14
        self.responder(0)
        self.relogio.agora = 16
        resposta = self.responder(self.pergunta().correta)
        self.assertFalse(resposta.timeout)
        self.assertEqual(resposta.pontos_ganhos, 230)

    def test_dados_coincidem_com_catalogo(self):
        self.assertEqual(len(PERGUNTAS), 15)
        self.assertEqual({p.categoria for p in PERGUNTAS}, {"geral", "tecnologia", "matematica"})


if __name__ == "__main__":
    unittest.main()
