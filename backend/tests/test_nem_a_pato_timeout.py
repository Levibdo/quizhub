from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select

from app.db.base import Base  # noqa: F401
from app.models import (
    DesafioNemPato,
    JogadorPartidaNemPato,
    PalpiteNemPato,
    PartidaNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import ParticipanteNemPatoStatus, RodadaNemPatoStatus
from tests.test_nem_a_pato_rodada import RodadaNemAPatoTestCase


class TestTimeoutNemAPato(RodadaNemAPatoTestCase):
    def preparar_timeout(self, nomes=("Levi", "Jorge", "Luana")):
        host = self.preparar(nomes)
        estado = self.iniciar_rodada(host)
        return host, estado.partida.rodada.id

    def definir_deadline(self, rodada_id, *, expirado):
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada_id)
            agora = datetime.now(timezone.utc)
            if expirado:
                rodada.iniciada_em = agora - timedelta(seconds=2)
                rodada.termina_em = agora - timedelta(seconds=1)
            else:
                rodada.termina_em = agora + timedelta(seconds=60)
            session.commit()

    def test_polling_antes_nao_finaliza_e_depois_finaliza_uma_vez(self):
        host, rodada_id = self.preparar_timeout()
        self.definir_deadline(rodada_id, expirado=False)
        antes = self.recuperar(host)
        self.assertEqual(antes.partida.rodada.status, "EM_ANDAMENTO")
        self.assertNotIn("resposta_numerica", antes.model_dump_json())
        versao = antes.sala.versao

        with self.sessions() as session:
            prazo = session.get(RodadaNemPato, rodada_id).termina_em
        instante_exato = (
            prazo.replace(tzinfo=timezone.utc) if prazo.tzinfo is None else prazo
        )
        self.service._agora_autoritativo = lambda _db: instante_exato
        resultado = self.recuperar(host)
        self.assertEqual(resultado.partida.rodada.status, "RESULTADO")
        self.assertEqual(resultado.partida.rodada.tipo_finalizacao, "SEM_PALPITE")
        self.assertIsNotNone(resultado.partida.rodada.finalizada_em)
        self.assertIsNone(resultado.partida.rodada.jogador_da_vez)
        self.assertEqual(resultado.sala.versao, versao + 1)
        self.assertIn("resposta_numerica", resultado.model_dump_json())
        self.assertIn("explicacao", resultado.model_dump_json())
        repetido = self.recuperar(host)
        self.assertEqual(repetido.sala.versao, resultado.sala.versao)
        self.assertTrue(all(j.patos == 0 for j in repetido.partida.jogadores))

    def test_timeout_com_palpite_protege_ultimo_autor_e_penaliza_demais(self):
        host, rodada_id = self.preparar_timeout()
        self.palpitar(host, "Levi", rodada_id, 999999)
        self.definir_deadline(rodada_id, expirado=True)
        resultado = self.recuperar(host)
        placar = {j.nome: j.patos for j in resultado.partida.jogadores}
        self.assertEqual(placar, {"Levi": 0, "Jorge": 1, "Luana": 1})
        rodada = resultado.partida.rodada
        self.assertEqual(rodada.tipo_finalizacao, "TEMPO_ESGOTADO")
        self.assertEqual(rodada.resultado_timeout.ultimo_palpite.valor, 999999)
        self.assertEqual(rodada.resultado_timeout.autor_protegido.nome, "Levi")
        self.assertIsNone(rodada.resultado_desafio)

    def test_seis_jogadores_patos_acumulam_e_abandonado_nao_recebe(self):
        nomes = ("A", "B", "C", "D", "E", "F")
        host, rodada_id = self.preparar_timeout(nomes)
        self.palpitar(host, "A", rodada_id, 1)
        with self.sessions() as session:
            partida = session.scalar(select(PartidaNemPato))
            jogadores = list(session.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
            ))
            for jogador in jogadores:
                jogador.patos = 2
            jogadores[-1].status = ParticipanteNemPatoStatus.ABANDONOU
            rodada = session.get(RodadaNemPato, rodada_id)
            agora = datetime.now(timezone.utc)
            rodada.iniciada_em = agora - timedelta(seconds=2)
            rodada.termina_em = agora - timedelta(seconds=1)
            session.commit()
        resultado = self.recuperar(host)
        placar = {j.nome: j.patos for j in resultado.partida.jogadores}
        self.assertEqual(placar["A"], 2)
        self.assertEqual([placar[nome] for nome in ("B", "C", "D", "E")], [3] * 4)
        self.assertEqual(placar["F"], 2)

    def test_palpite_e_desafio_tardios_convergem_sem_criar_registros(self):
        host, rodada_id = self.preparar_timeout()
        self.palpitar(host, "Levi", rodada_id, 10)
        self.definir_deadline(rodada_id, expirado=True)
        with self.sessions() as session:
            estado = self.service.desafiar(
                session,
                host.sala.codigo,
                rodada_id,
                self.tokens_by_name["Jorge"],
                uuid4(),
            )
        self.assertEqual(estado.partida.rodada.tipo_finalizacao, "TEMPO_ESGOTADO")
        with self.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(DesafioNemPato)), 0)
            self.assertEqual(session.scalar(select(func.count()).select_from(PalpiteNemPato)), 1)

        host2, rodada2 = self.preparar_timeout(("G", "H", "I"))
        self.definir_deadline(rodada2, expirado=True)
        with self.sessions() as session:
            estado2 = self.service.palpitar(
                session, host2.sala.codigo, rodada2,
                host2.credencial_participante, 10, uuid4(),
            )
        self.assertEqual(estado2.partida.rodada.tipo_finalizacao, "SEM_PALPITE")
        with self.sessions() as session:
            quantidade = session.scalar(
                select(func.count()).select_from(PalpiteNemPato)
                .where(PalpiteNemPato.rodada_id == rodada2)
            )
        self.assertEqual(quantidade, 0)

    def test_host_avanca_apos_timeout_preservando_placar(self):
        host, rodada_id = self.preparar_timeout()
        self.palpitar(host, "Levi", rodada_id, 10)
        self.definir_deadline(rodada_id, expirado=True)
        resultado = self.recuperar(host)
        placar = {j.nome: j.patos for j in resultado.partida.jogadores}
        with self.sessions() as session:
            seguinte = self.service.iniciar_proxima_rodada(
                session, host.sala.codigo, rodada_id,
                host.credencial_participante,
            )
        self.assertEqual(seguinte.partida.rodada.numero, 2)
        self.assertEqual(
            {j.nome: j.patos for j in seguinte.partida.jogadores}, placar
        )
        self.assertNotIn("resposta_numerica", seguinte.model_dump_json())
