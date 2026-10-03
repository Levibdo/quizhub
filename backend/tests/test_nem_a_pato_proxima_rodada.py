from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.db.base import Base  # noqa: F401
from app.models import (
    JogadorPartidaNemPato,
    PalpiteNemPato,
    PartidaNemPato,
    ParticipanteNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import ParticipanteNemPatoStatus, RodadaNemPatoStatus
from tests.test_nem_a_pato_rodada import RodadaNemAPatoTestCase


class TestProximaRodadaNemAPato(RodadaNemAPatoTestCase):
    def preparar_resultado(self, nomes=("Levi", "Jorge", "Luana")):
        host = self.preparar(nomes)
        estado = self.iniciar_rodada(host)
        rodada_id = estado.partida.rodada.id
        self.palpitar(host, nomes[0], rodada_id, 1)
        with self.sessions() as session:
            self.service.desafiar(
                session,
                host.sala.codigo,
                rodada_id,
                self.tokens_by_name[nomes[1]],
                uuid4(),
            )
        return host, rodada_id

    def avancar(self, host, rodada_id, token=None):
        with self.sessions() as session:
            return self.service.iniciar_proxima_rodada(
                session,
                host.sala.codigo,
                rodada_id,
                token or host.credencial_participante,
            )

    def test_host_avanca_r1_r2_atomicamente_e_preserva_historico_e_patos(self):
        host, rodada_id = self.preparar_resultado()
        antes = self.recuperar(host)
        patos = {j.nome: j.patos for j in antes.partida.jogadores}
        versao = antes.sala.versao
        estado = self.avancar(host, rodada_id)
        rodada = estado.partida.rodada
        self.assertEqual((estado.partida.rodada_atual, rodada.numero), (2, 2))
        self.assertEqual(rodada.status, "EM_ANDAMENTO")
        self.assertEqual(rodada.jogador_inicial.nome, "Jorge")
        self.assertEqual(rodada.jogador_da_vez.nome, "Jorge")
        self.assertEqual(rodada.palpites, [])
        self.assertIsNone(rodada.maior_palpite)
        self.assertEqual(estado.sala.versao, versao + 1)
        self.assertEqual({j.nome: j.patos for j in estado.partida.jogadores}, patos)
        self.assertEqual(int((rodada.termina_em - rodada.iniciada_em).total_seconds()), 120)
        serializado = estado.model_dump_json()
        self.assertNotIn("resposta_numerica", serializado)
        self.assertNotIn("explicacao", serializado)
        with self.sessions() as session:
            anterior = session.get(RodadaNemPato, rodada_id)
            self.assertEqual(anterior.status, RodadaNemPatoStatus.RESULTADO)
            self.assertEqual(session.scalar(select(PalpiteNemPato).where(PalpiteNemPato.rodada_id == rodada_id)).valor, 1)

    def test_nao_host_estado_incorreto_rodada_errada_e_menos_de_tres_rejeitam(self):
        host, rodada_id = self.preparar_resultado()
        with self.assertRaises(Exception) as nao_host:
            self.avancar(host, rodada_id, self.tokens_by_name["Jorge"])
        self.assertEqual(nao_host.exception.status_code, 403)
        with self.assertRaises(Exception) as errada:
            self.avancar(host, rodada_id + 999)
        self.assertEqual(errada.exception.status_code, 409)

        outro = self.preparar(("A", "B", "C"))
        ativa = self.iniciar_rodada(outro)
        with self.assertRaises(Exception) as andamento:
            self.avancar(outro, ativa.partida.rodada.id)
        self.assertEqual(andamento.exception.status_code, 409)

        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            jogador = session.scalar(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id, JogadorPartidaNemPato.nome_snapshot == "Luana"))
            jogador.status = ParticipanteNemPatoStatus.ABANDONOU
            session.commit()
        with self.assertRaises(Exception) as poucos:
            self.avancar(host, rodada_id)
        self.assertIn("3 jogadores ativos", poucos.exception.detail)

    def test_rotacao_com_seis_e_abandonado_excluido(self):
        host, rodada_id = self.preparar_resultado(("A", "B", "C", "D", "E", "F"))
        estado = self.avancar(host, rodada_id)
        self.assertEqual(estado.partida.rodada.jogador_inicial.nome, "B")

        host2, rodada2 = self.preparar_resultado(("G", "H", "I", "J"))
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host2.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            abandonado = session.scalar(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id, JogadorPartidaNemPato.nome_snapshot == "H"))
            abandonado.status = ParticipanteNemPatoStatus.ABANDONOU
            session.commit()
        estado = self.avancar(host2, rodada2)
        self.assertEqual(estado.partida.rodada.jogador_inicial.nome, "I")
        self.assertEqual(next(j.nome for j in estado.partida.jogadores if j.status == "ABANDONOU"), "H")

    def test_host_abandona_no_resultado_e_novo_host_avanca(self):
        host, rodada_id = self.preparar_resultado(("Levi", "Jorge", "Luana", "Bia"))
        antes = self.recuperar(host)
        patos = {j.nome: j.patos for j in antes.partida.jogadores}
        with self.sessions() as session:
            sala = self.service.abandonar(
                session, host.sala.codigo, host.credencial_participante
            )
        self.assertEqual(
            next(p.nome for p in sala.participantes if p.eh_anfitriao), "Jorge"
        )
        with self.sessions() as session:
            estado = self.service.iniciar_proxima_rodada(
                session,
                host.sala.codigo,
                rodada_id,
                self.tokens_by_name["Jorge"],
            )
        self.assertEqual(estado.partida.rodada.numero, 2)
        self.assertEqual(estado.partida.rodada.jogador_inicial.nome, "Luana")
        self.assertEqual(
            next(j.status for j in estado.partida.jogadores if j.nome == "Levi"),
            "ABANDONOU",
        )
        self.assertEqual(
            {j.nome: j.patos for j in estado.partida.jogadores}, patos
        )

    def test_rodada_dez_nao_avanca(self):
        host, rodada_id = self.preparar_resultado()
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            r1 = session.get(RodadaNemPato, rodada_id)
            r10 = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 10))
            r1.status = RodadaNemPatoStatus.AGUARDANDO_INICIO
            r10.status = RodadaNemPatoStatus.RESULTADO
            r10.finalizada_em = r1.finalizada_em
            partida.rodada_atual = 10
            session.commit()
            rodada10_id = r10.id
        with self.assertRaises(Exception) as fim:
            self.avancar(host, rodada10_id)
        self.assertIn("não há próxima rodada", fim.exception.detail)
