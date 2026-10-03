import unittest
from uuid import uuid4

from sqlalchemy import select

from app.db.base import Base  # noqa: F401

from app.models import (
    DesafioNemPato,
    JogadorPartidaNemPato,
    PalpiteNemPato,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import RodadaNemPatoStatus, TipoFinalizacaoRodadaNemPato
from tests.test_nem_a_pato_rodada import RodadaNemAPatoTestCase


class TestDesafioNemAPato(RodadaNemAPatoTestCase):
    def setUp(self):
        super().setUp()
        self.host = self.preparar()
        self.estado = self.iniciar_rodada(self.host)
        self.rodada_id = self.estado.partida.rodada.id

    def desafiar(self, nome, action_id=None):
        with self.sessions() as session:
            return self.service.desafiar(
                session,
                self.host.sala.codigo,
                self.rodada_id,
                self.tokens_by_name[nome],
                action_id or uuid4(),
            )

    def resposta(self, valor):
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, self.rodada_id)
            pergunta = session.get(PerguntaNemPato, rodada.pergunta_id)
            pergunta.resposta_numerica = valor
            session.commit()

    def persistido(self):
        with self.sessions() as session:
            sala = session.scalar(
                select(SalaNemPato).where(SalaNemPato.codigo == self.host.sala.codigo)
            )
            rodada = session.get(RodadaNemPato, self.rodada_id)
            desafio = session.scalar(
                select(DesafioNemPato).where(DesafioNemPato.rodada_id == self.rodada_id)
            )
            jogadores = list(session.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == rodada.partida_id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
            ))
            return sala, rodada, desafio, jogadores

    def test_sem_palpite_autor_token_e_rodada_errada_sao_rejeitados(self):
        with self.assertRaises(Exception) as vazio:
            self.desafiar("Jorge")
        self.assertEqual(vazio.exception.status_code, 409)
        self.palpitar(self.host, "Levi", self.rodada_id, 1)
        with self.assertRaises(Exception) as autor:
            self.desafiar("Levi")
        self.assertIn("próprio palpite", autor.exception.detail)
        with self.sessions() as session:
            with self.assertRaises(Exception) as token:
                self.service.desafiar(
                    session, self.host.sala.codigo, self.rodada_id, "inválido", uuid4()
                )
        self.assertEqual(token.exception.status_code, 401)
        with self.sessions() as session:
            with self.assertRaises(Exception) as rodada:
                self.service.desafiar(
                    session,
                    self.host.sala.codigo,
                    self.rodada_id + 999,
                    self.tokens_by_name["Jorge"],
                    uuid4(),
                )
        self.assertEqual(rodada.exception.status_code, 404)

    def test_fora_de_turno_pode_desafiar_e_autor_perde_quando_passa(self):
        self.resposta(500)
        self.palpitar(self.host, "Levi", self.rodada_id, 700)
        antes = self.recuperar(self.host).sala.versao
        estado = self.desafiar("Luana")
        rodada = estado.partida.rodada
        self.assertEqual(rodada.status, "RESULTADO")
        self.assertEqual(rodada.tipo_finalizacao, "DESAFIO")
        self.assertEqual(rodada.resultado_desafio.desafiante.nome, "Luana")
        self.assertEqual(rodada.resultado_desafio.palpite_desafiado.valor, 700)
        self.assertEqual(rodada.resultado_desafio.palpite_desafiado.jogador.nome, "Levi")
        self.assertEqual(rodada.resultado_desafio.jogador_penalizado.nome, "Levi")
        self.assertEqual(next(j.patos for j in estado.partida.jogadores if j.nome == "Levi"), 1)
        self.assertEqual(estado.sala.versao, antes + 1)
        self.assertEqual(rodada.pergunta.resposta_numerica, 500)
        self.assertEqual(rodada.pergunta.explicacao, "Explicação privada de teste.")

    def test_menor_e_igual_penalizam_desafiante(self):
        for resposta, palpite in ((500, 400), (500, 500)):
            with self.subTest(resposta=resposta, palpite=palpite):
                if palpite == 500:
                    self.tearDown()
                    self.setUp()
                self.resposta(resposta)
                self.palpitar(self.host, "Levi", self.rodada_id, palpite)
                estado = self.desafiar("Jorge")
                self.assertEqual(
                    estado.partida.rodada.resultado_desafio.jogador_penalizado.nome,
                    "Jorge",
                )
                self.assertEqual(next(j.patos for j in estado.partida.jogadores if j.nome == "Jorge"), 1)

    def test_retry_apos_resultado_e_idempotente_e_nova_acao_nao_altera(self):
        self.resposta(10)
        self.palpitar(self.host, "Levi", self.rodada_id, 5)
        action_id = uuid4()
        primeiro = self.desafiar("Jorge", action_id)
        segundo = self.desafiar("Jorge", action_id)
        self.assertEqual(segundo.sala.versao, primeiro.sala.versao)
        self.assertEqual(sum(j.patos for j in segundo.partida.jogadores), 1)
        penalizado = segundo.partida.rodada.resultado_desafio.jogador_penalizado.id
        with self.assertRaises(Exception) as outra:
            self.desafiar("Luana")
        self.assertEqual(outra.exception.status_code, 409)
        recuperado = self.recuperar(self.host)
        self.assertEqual(sum(j.patos for j in recuperado.partida.jogadores), 1)
        self.assertEqual(
            recuperado.partida.rodada.resultado_desafio.jogador_penalizado.id,
            penalizado,
        )

    def test_resultado_bloqueia_novos_palpites_e_persiste_campos(self):
        self.resposta(10)
        self.palpitar(self.host, "Levi", self.rodada_id, 5)
        self.desafiar("Jorge")
        with self.assertRaises(Exception) as palpite:
            self.palpitar(self.host, "Jorge", self.rodada_id, 6)
        self.assertEqual(palpite.exception.status_code, 409)
        sala, rodada, desafio, jogadores = self.persistido()
        self.assertEqual(rodada.status, RodadaNemPatoStatus.RESULTADO)
        self.assertEqual(rodada.tipo_finalizacao, TipoFinalizacaoRodadaNemPato.DESAFIO)
        self.assertIsNotNone(rodada.finalizada_em)
        self.assertIsNotNone(desafio)
        self.assertEqual(sum(j.patos for j in jogadores), 1)
        self.assertEqual(sala.estado_versao, 6)

    def test_endpoint_desafiar_revela_resultado_sem_segredos_de_credencial(self):
        self.resposta(10)
        self.palpitar(self.host, "Levi", self.rodada_id, 5)
        with self.client() as client:
            resposta = client.post(
                f"/api/v1/nem-pato/salas/{self.host.sala.codigo}/rodadas/{self.rodada_id}/desafiar",
                headers={"X-Nem-Pato-Token": self.tokens_by_name["Jorge"]},
                json={"client_action_id": str(uuid4())},
            )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        corpo = resposta.json()
        self.assertEqual(corpo["partida"]["rodada"]["status"], "RESULTADO")
        self.assertEqual(corpo["partida"]["rodada"]["pergunta"]["resposta_numerica"], 10)
        self.assertIn("explicacao", corpo["partida"]["rodada"]["pergunta"])
        for segredo in ("token_hash", "credencial_participante"):
            self.assertNotIn(segredo, resposta.text)


if __name__ == "__main__":
    unittest.main()
