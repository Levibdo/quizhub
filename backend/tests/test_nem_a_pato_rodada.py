import unittest
from uuid import uuid4

from sqlalchemy import func, select

from app.db.base import Base  # noqa: F401
from app.models import (
    JogadorPartidaNemPato,
    PalpiteNemPato,
    PartidaNemPato,
    ParticipanteNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import (
    PartidaNemPatoStatus,
    ParticipanteNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
)
from app.services.salas_nem_a_pato import hash_credencial
from tests.test_nem_a_pato_iniciar import InicioNemAPatoTestCase


class RodadaNemAPatoTestCase(InicioNemAPatoTestCase):
    def preparar(self, nomes=("Levi", "Jorge", "Luana")):
        host = self.sala_com(list(nomes))
        self.iniciar(host)
        return host

    def iniciar_rodada(self, host, token=None):
        with self.sessions() as session:
            return self.service.iniciar_rodada(
                session,
                host.sala.codigo,
                token or host.credencial_participante,
            )

    def palpitar(self, host, nome, rodada_id, valor, action_id=None):
        with self.sessions() as session:
            return self.service.palpitar(
                session,
                host.sala.codigo,
                rodada_id,
                self.tokens_by_name[nome],
                valor,
                action_id or uuid4(),
            )

    def recuperar(self, host, token=None):
        with self.sessions() as session:
            return self.service.recuperar(
                session,
                host.sala.codigo,
                token or host.credencial_participante,
            )

    def rodada_db(self, codigo, numero=1):
        with self.sessions() as session:
            sala = session.scalar(
                select(SalaNemPato).where(SalaNemPato.codigo == codigo)
            )
            partida = session.scalar(
                select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)
            )
            rodada = session.scalar(
                select(RodadaNemPato).where(
                    RodadaNemPato.partida_id == partida.id,
                    RodadaNemPato.numero == numero,
                )
            )
            return sala, partida, rodada


class TestInicioRodadaNemAPato(RodadaNemAPatoTestCase):
    def test_host_inicia_rodada_com_deadline_turno_e_pergunta_segura(self):
        host = self.preparar()
        antes = self.recuperar(host)
        self.assertIsNone(antes.partida.rodada.pergunta)

        estado = self.iniciar_rodada(host)
        rodada = estado.partida.rodada
        self.assertEqual((estado.partida.rodada_atual, rodada.numero), (1, 1))
        self.assertEqual(rodada.status, "EM_ANDAMENTO")
        self.assertEqual(rodada.jogador_inicial.nome, "Levi")
        self.assertEqual(rodada.jogador_da_vez.nome, "Levi")
        self.assertTrue(rodada.jogador_da_vez.eh_eu)
        self.assertIsNotNone(rodada.pergunta)
        self.assertEqual(
            int((rodada.termina_em - rodada.iniciada_em).total_seconds()), 120
        )
        serializado = estado.model_dump_json()
        for segredo in (
            "resposta_numerica",
            "explicacao",
            "token_hash",
            "credencial_participante",
        ):
            self.assertNotIn(segredo, serializado)

    def test_nao_host_token_invalido_host_abandonado_e_sala_inexistente(self):
        host = self.preparar()
        with self.sessions() as session:
            with self.assertRaises(Exception) as nao_host:
                self.service.iniciar_rodada(
                    session, host.sala.codigo, self.tokens_by_name["Jorge"]
                )
        self.assertEqual(nao_host.exception.status_code, 403)

        with self.sessions() as session:
            with self.assertRaises(Exception) as invalido:
                self.service.iniciar_rodada(session, host.sala.codigo, "inválido")
        self.assertEqual(invalido.exception.status_code, 401)

        with self.sessions() as session:
            participante = session.scalar(
                select(ParticipanteNemPato).where(
                    ParticipanteNemPato.token_hash
                    == hash_credencial(host.credencial_participante)
                )
            )
            participante.status = ParticipanteNemPatoStatus.ABANDONOU
            participante.eh_anfitriao = False
            participante.saiu_em = func.now()
            session.commit()
        with self.sessions() as session:
            with self.assertRaises(Exception) as abandonado:
                self.service.iniciar_rodada(
                    session, host.sala.codigo, host.credencial_participante
                )
        self.assertEqual(abandonado.exception.status_code, 403)

        with self.sessions() as session:
            with self.assertRaises(Exception) as inexistente:
                self.service.iniciar_rodada(session, "XXXXXX", "token")
        self.assertEqual(inexistente.exception.status_code, 404)

    def test_rejeita_sala_e_partida_em_estado_incorreto(self):
        host_aguardando = self.sala_com(["A", "B", "C"])
        with self.sessions() as session:
            with self.assertRaises(Exception) as sala:
                self.service.iniciar_rodada(
                    session,
                    host_aguardando.sala.codigo,
                    host_aguardando.credencial_participante,
                )
        self.assertEqual(sala.exception.status_code, 409)

        host = self.preparar(("D", "E", "F"))
        with self.sessions() as session:
            sala_db = session.scalar(
                select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo)
            )
            partida = session.scalar(
                select(PartidaNemPato).where(PartidaNemPato.sala_id == sala_db.id)
            )
            partida.status = PartidaNemPatoStatus.CANCELADA
            session.commit()
        with self.sessions() as session:
            with self.assertRaises(Exception) as partida:
                self.service.iniciar_rodada(
                    session, host.sala.codigo, host.credencial_participante
                )
        self.assertEqual(partida.exception.status_code, 409)

    def test_duplo_inicio_rejeita_sem_corromper_timestamps_ou_versao(self):
        host = self.preparar()
        primeira = self.iniciar_rodada(host)
        versao = primeira.sala.versao
        inicio = primeira.partida.rodada.iniciada_em
        with self.sessions() as session:
            with self.assertRaises(Exception) as repetida:
                self.service.iniciar_rodada(
                    session, host.sala.codigo, host.credencial_participante
                )
        self.assertEqual(repetida.exception.status_code, 409)
        recuperada = self.recuperar(host)
        self.assertEqual(recuperada.sala.versao, versao)
        self.assertEqual(
            recuperada.partida.rodada.iniciada_em.replace(tzinfo=None),
            inicio.replace(tzinfo=None),
        )

    def test_rotacao_inicial_generaliza_tres_e_seis_jogadores(self):
        for nomes in (
            ("A", "B", "C"),
            ("A", "B", "C", "D", "E", "F"),
        ):
            with self.subTest(jogadores=len(nomes)):
                host = self.preparar(nomes)
                _, _, jogadores, _ = self.contagens(host.sala.codigo)
                obtidos = [
                    self.service._jogador_inicial_da_rodada(jogadores, numero).nome_snapshot
                    for numero in range(1, len(nomes) + 2)
                ]
                self.assertEqual(obtidos, list(nomes) + [nomes[0]])


class TestPalpitesNemAPato(RodadaNemAPatoTestCase):
    def setUp(self):
        super().setUp()
        self.host = self.preparar()
        self.estado = self.iniciar_rodada(self.host)
        self.rodada_id = self.estado.partida.rodada.id

    def test_zero_positivo_turno_e_wraparound(self):
        estado = self.palpitar(self.host, "Levi", self.rodada_id, 0)
        self.assertEqual(estado.partida.rodada.maior_palpite, 0)
        self.assertEqual(estado.partida.rodada.jogador_da_vez.nome, "Jorge")
        estado = self.palpitar(self.host, "Jorge", self.rodada_id, 100)
        self.assertEqual(estado.partida.rodada.jogador_da_vez.nome, "Luana")
        estado = self.palpitar(self.host, "Luana", self.rodada_id, 200)
        self.assertEqual(estado.partida.rodada.jogador_da_vez.nome, "Levi")
        self.assertEqual(
            [(p.jogador.nome, p.valor) for p in estado.partida.rodada.palpites],
            [("Levi", 0), ("Jorge", 100), ("Luana", 200)],
        )

    def test_apenas_jogador_da_vez_e_crescimento_estrito(self):
        with self.assertRaises(Exception) as fora_turno:
            self.palpitar(self.host, "Jorge", self.rodada_id, 1)
        self.assertEqual(fora_turno.exception.status_code, 409)
        self.palpitar(self.host, "Levi", self.rodada_id, 100)
        for valor in (100, 99):
            with self.subTest(valor=valor):
                with self.assertRaises(Exception) as baixo:
                    self.palpitar(self.host, "Jorge", self.rodada_id, valor)
                self.assertIn("maior que 100", baixo.exception.detail)
        estado = self.palpitar(self.host, "Jorge", self.rodada_id, 101)
        self.assertEqual(estado.partida.rodada.maior_palpite, 101)

    def test_retry_idempotente_nao_duplica_nem_avanca_turno(self):
        action_id = uuid4()
        primeira = self.palpitar(
            self.host, "Levi", self.rodada_id, 100, action_id
        )
        repetida = self.palpitar(
            self.host, "Levi", self.rodada_id, 100, action_id
        )
        self.assertEqual(len(repetida.partida.rodada.palpites), 1)
        self.assertEqual(repetida.partida.rodada.jogador_da_vez.nome, "Jorge")
        self.assertEqual(repetida.sala.versao, primeira.sala.versao)

    def test_client_action_id_incompativel_rejeitado(self):
        action_id = uuid4()
        self.palpitar(self.host, "Levi", self.rodada_id, 100, action_id)
        with self.assertRaises(Exception) as valor:
            self.palpitar(self.host, "Levi", self.rodada_id, 200, action_id)
        self.assertIn("client_action_id", valor.exception.detail)
        with self.assertRaises(Exception) as jogador:
            self.palpitar(self.host, "Jorge", self.rodada_id, 100, action_id)
        self.assertIn("client_action_id", jogador.exception.detail)

    def test_rodada_errada_token_invalido_e_participante_abandonado(self):
        with self.sessions() as session:
            with self.assertRaises(Exception) as rodada:
                self.service.palpitar(
                    session,
                    self.host.sala.codigo,
                    self.rodada_id + 999,
                    self.host.credencial_participante,
                    1,
                    uuid4(),
                )
        self.assertEqual(rodada.exception.status_code, 404)
        with self.sessions() as session:
            with self.assertRaises(Exception) as token:
                self.service.palpitar(
                    session,
                    self.host.sala.codigo,
                    self.rodada_id,
                    "inválido",
                    1,
                    uuid4(),
                )
        self.assertEqual(token.exception.status_code, 401)
        with self.sessions() as session:
            participante = session.scalar(
                select(ParticipanteNemPato).where(
                    ParticipanteNemPato.nome == "Levi"
                )
            )
            participante.status = ParticipanteNemPatoStatus.ABANDONOU
            session.commit()
        with self.sessions() as session:
            with self.assertRaises(Exception) as abandonado:
                self.service.palpitar(
                    session,
                    self.host.sala.codigo,
                    self.rodada_id,
                    self.host.credencial_participante,
                    1,
                    uuid4(),
                )
        self.assertEqual(abandonado.exception.status_code, 403)

    def test_recuperacao_reconstroi_pergunta_historico_maior_e_turno(self):
        self.palpitar(self.host, "Levi", self.rodada_id, 100)
        self.palpitar(self.host, "Jorge", self.rodada_id, 200)
        self.palpitar(self.host, "Luana", self.rodada_id, 500)
        with self.sessions() as session:
            recuperada = self.service.recuperar(
                session,
                self.host.sala.codigo,
                self.tokens_by_name["Jorge"],
            )
        rodada = recuperada.partida.rodada
        self.assertIsNotNone(rodada.pergunta.enunciado)
        self.assertEqual([p.valor for p in rodada.palpites], [100, 200, 500])
        self.assertEqual(rodada.maior_palpite, 500)
        self.assertEqual(rodada.jogador_da_vez.nome, "Levi")
        self.assertFalse(rodada.jogador_da_vez.eh_eu)
        for segredo in ("resposta_numerica", "explicacao", "token_hash"):
            self.assertNotIn(segredo, recuperada.model_dump_json())


class TestRodadaNemAPatoApi(RodadaNemAPatoTestCase):
    def test_payload_estrito_rejeita_bool_float_string_negativo_e_overflow(self):
        host = self.preparar()
        estado = self.iniciar_rodada(host)
        rodada_id = estado.partida.rodada.id
        valores = (True, 1.5, "1", -1, 9_223_372_036_854_775_808)
        with self.client() as client:
            for valor in valores:
                with self.subTest(valor=valor):
                    resposta = client.post(
                        f"/api/v1/nem-pato/salas/{host.sala.codigo}/rodadas/{rodada_id}/palpites",
                        headers={
                            "X-Nem-Pato-Token": host.credencial_participante
                        },
                        json={"valor": valor, "client_action_id": str(uuid4())},
                    )
                    self.assertEqual(resposta.status_code, 422, resposta.text)

    def test_endpoints_iniciam_e_registram_sem_expor_segredos(self):
        host = self.preparar()
        with self.client() as client:
            inicio = client.post(
                f"/api/v1/nem-pato/salas/{host.sala.codigo}/rodadas/iniciar",
                headers={"X-Nem-Pato-Token": host.credencial_participante},
            )
            self.assertEqual(inicio.status_code, 200, inicio.text)
            rodada_id = inicio.json()["partida"]["rodada"]["id"]
            palpite = client.post(
                f"/api/v1/nem-pato/salas/{host.sala.codigo}/rodadas/{rodada_id}/palpites",
                headers={"X-Nem-Pato-Token": host.credencial_participante},
                json={"valor": 0, "client_action_id": str(uuid4())},
            )
        self.assertEqual(palpite.status_code, 200, palpite.text)
        self.assertEqual(palpite.json()["partida"]["rodada"]["maior_palpite"], 0)
        for resposta in (inicio, palpite):
            for segredo in (
                "resposta_numerica",
                "explicacao",
                "token_hash",
                "credencial_participante",
            ):
                self.assertNotIn(segredo, resposta.text)


if __name__ == "__main__":
    unittest.main()
