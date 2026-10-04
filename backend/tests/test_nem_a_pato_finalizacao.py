from datetime import datetime, timedelta, timezone
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
from app.nem_a_pato import (
    PartidaNemPatoStatus,
    ParticipanteNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
)
from tests.test_nem_a_pato_rodada import RodadaNemAPatoTestCase


class TestFinalizacaoNemAPato(RodadaNemAPatoTestCase):
    @staticmethod
    def expirar(rodada):
        agora = datetime.now(timezone.utc)
        rodada.iniciada_em = agora - timedelta(seconds=2)
        rodada.termina_em = agora - timedelta(seconds=1)

    def preparar_r10(self, nomes=("Levi", "Jorge", "Luana"), patos=None):
        host = self.preparar(nomes)
        self.iniciar_rodada(host)
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            jogadores = list(session.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
            ))
            r1 = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 1))
            r10 = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 10))
            r1.status = RodadaNemPatoStatus.RESULTADO
            agora = datetime.now(timezone.utc)
            r10.status = RodadaNemPatoStatus.EM_ANDAMENTO
            r10.jogador_inicial_id = jogadores[0].id
            r10.jogador_da_vez_id = jogadores[0].id
            r10.iniciada_em = agora
            r10.termina_em = agora + timedelta(seconds=120)
            partida.rodada_atual = 10
            for jogador, quantidade in zip(jogadores, patos or [0] * len(jogadores)):
                jogador.patos = quantidade
            session.commit()
            return host, r10.id

    def test_r1_a_r9_nao_finalizam_e_r10_desafio_finaliza_com_pato_atualizado(self):
        host = self.preparar()
        estado = self.iniciar_rodada(host)
        rodada_id = estado.partida.rodada.id
        self.palpitar(host, "Levi", rodada_id, 9_000_000_000)
        with self.sessions() as session:
            resultado = self.service.desafiar(
                session, host.sala.codigo, rodada_id,
                self.tokens_by_name["Jorge"], uuid4(),
            )
        self.assertEqual(resultado.partida.status, "EM_ANDAMENTO")
        self.assertEqual(resultado.sala.status, "EM_PARTIDA")

        host, rodada_id = self.preparar_r10(patos=[1, 2, 4])
        self.palpitar(host, "Levi", rodada_id, 9_000_000_000)
        with self.sessions() as session:
            resultado = self.service.desafiar(
                session, host.sala.codigo, rodada_id,
                self.tokens_by_name["Jorge"], uuid4(),
            )
        self.assertEqual(resultado.partida.status, "FINALIZADA")
        self.assertEqual(resultado.sala.status, "ENCERRADA")
        self.assertEqual(resultado.partida.rodada.status, "RESULTADO")
        self.assertEqual([j.nome for j in resultado.partida.resultado_final.vencedores], ["Levi", "Jorge"])
        self.assertEqual([j.nome for j in resultado.partida.resultado_final.patos_da_partida], ["Luana"])
        self.assertEqual(next(j.patos for j in resultado.partida.jogadores if j.nome == "Levi"), 2)

    def test_r10_timeout_e_sem_palpite_finalizam_depois_das_penalizacoes(self):
        host, rodada_id = self.preparar_r10(patos=[0, 0, 2])
        self.palpitar(host, "Levi", rodada_id, 10)
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada_id)
            self.expirar(rodada)
            session.commit()
        resultado = self.recuperar(host)
        self.assertEqual(resultado.partida.status, "FINALIZADA")
        self.assertEqual({j.nome: j.patos for j in resultado.partida.jogadores}, {"Levi": 0, "Jorge": 1, "Luana": 3})
        self.assertEqual([j.nome for j in resultado.partida.resultado_final.vencedores], ["Levi"])
        self.assertEqual([j.nome for j in resultado.partida.resultado_final.patos_da_partida], ["Luana"])

        host2, rodada2 = self.preparar_r10(("A", "B", "C"), [2, 2, 2])
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada2)
            self.expirar(rodada)
            session.commit()
        empate = self.recuperar(host2)
        self.assertTrue(empate.partida.resultado_final.empate_geral)
        self.assertEqual(len(empate.partida.resultado_final.vencedores), 3)
        self.assertEqual(len(empate.partida.resultado_final.patos_da_partida), 3)
        self.assertEqual({j.patos for j in empate.partida.jogadores}, {2})

    def test_empates_seis_jogadores_e_abandonado_fora_dos_extremos(self):
        nomes = ("A", "B", "C", "D", "E", "F")
        host, rodada_id = self.preparar_r10(nomes, [1, 1, 3, 5, 5, 0])
        with self.sessions() as session:
            partida = session.scalar(select(PartidaNemPato).join(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            abandonado = session.scalar(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id, JogadorPartidaNemPato.nome_snapshot == "F"))
            abandonado.status = ParticipanteNemPatoStatus.ABANDONOU
            rodada = session.get(RodadaNemPato, rodada_id)
            self.expirar(rodada)
            session.commit()
        resultado = self.recuperar(host).partida.resultado_final
        self.assertEqual([j.nome for j in resultado.vencedores], ["A", "B"])
        self.assertEqual([j.nome for j in resultado.patos_da_partida], ["D", "E"])
        self.assertEqual([j.nome for j in resultado.abandonados], ["F"])

    def test_cancelamento_com_menos_de_tres_ativos_nao_tem_resultado(self):
        host = self.preparar(("A", "B", "C"))
        estado = self.iniciar_rodada(host)
        self.palpitar(host, "A", estado.partida.rodada.id, 10)
        with self.sessions() as session:
            self.service.desafiar(session, host.sala.codigo, estado.partida.rodada.id, self.tokens_by_name["B"], uuid4())
        with self.sessions() as session:
            self.service.abandonar(session, host.sala.codigo, self.tokens_by_name["C"])
        cancelada = self.recuperar(host)
        self.assertEqual(cancelada.sala.status, "ENCERRADA")
        self.assertEqual(cancelada.partida.status, "CANCELADA")
        self.assertIsNone(cancelada.partida.resultado_final)

    def test_estado_terminal_e_imutavel_e_f5_reconstroi_resultado(self):
        host, rodada_id = self.preparar_r10(patos=[0, 1, 2])
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada_id)
            self.expirar(rodada)
            session.commit()
        final = self.recuperar(host)
        versao = final.sala.versao
        repetido = self.recuperar(host)
        self.assertEqual(repetido.sala.versao, versao)
        self.assertEqual(repetido.partida.resultado_final, final.partida.resultado_final)
        with self.sessions() as session:
            with self.assertRaises(Exception) as palpite:
                self.service.palpitar(session, host.sala.codigo, rodada_id, host.credencial_participante, 1, uuid4())
        self.assertEqual(palpite.exception.status_code, 409)
        with self.sessions() as session:
            with self.assertRaises(Exception) as proxima:
                self.service.iniciar_proxima_rodada(session, host.sala.codigo, rodada_id, host.credencial_participante)
        self.assertEqual(proxima.exception.status_code, 409)
