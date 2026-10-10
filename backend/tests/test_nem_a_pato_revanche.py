from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from uuid import uuid4

from app.conteudo import MODO_NEM_A_PATO, ORIGEM_USUARIO
from app.db.base import Base  # noqa: F401
from app.models import (
    Categoria,
    JogadorPartidaNemPato,
    PartidaNemPato,
    ParticipanteNemPato,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
    Usuario,
)
from app.nem_a_pato import (
    PartidaNemPatoStatus,
    ParticipanteNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
)
from tests.test_nem_a_pato_finalizacao import TestFinalizacaoNemAPato


class TestRevancheNemAPato(TestFinalizacaoNemAPato):
    def finalizar_primeira(self, nomes=("Levi", "Jorge", "Luana"), catalogo=30):
        if catalogo > 12:
            self.perguntas(catalogo - 12)
        host, rodada_id = self.preparar_r10(nomes, list(range(len(nomes))))
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada_id)
            self.expirar(rodada)
            session.commit()
        final = self.recuperar(host)
        self.assertEqual(final.partida.status, "FINALIZADA")
        return host, final

    def revanche(self, host, token=None):
        with self.sessions() as session:
            return self.service.jogar_novamente(
                session, host.sala.codigo,
                token or host.credencial_participante,
            )

    def partidas(self, codigo):
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partidas = list(session.scalars(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id).order_by(PartidaNemPato.numero)))
            dados = []
            for partida in partidas:
                jogadores = list(session.scalars(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id).order_by(JogadorPartidaNemPato.ordem_circular)))
                rodadas = list(session.scalars(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id).order_by(RodadaNemPato.numero)))
                dados.append((partida, jogadores, rodadas))
            return sala, dados

    def test_host_cria_partida_2_na_mesma_sala_com_estado_limpo(self):
        host, final = self.finalizar_primeira()
        versao = final.sala.versao
        nova = self.revanche(host)
        self.assertEqual((nova.sala.status, nova.sala.versao), ("EM_PARTIDA", versao + 1))
        self.assertEqual((nova.partida.numero, nova.partida.status, nova.partida.rodada_atual), (2, "EM_ANDAMENTO", 0))
        self.assertEqual([j.patos for j in nova.partida.jogadores], [0, 0, 0])
        self.assertEqual([j.ordem_circular for j in nova.partida.jogadores], [1, 2, 3])
        self.assertEqual(nova.partida.rodada.status, "AGUARDANDO_INICIO")
        self.assertIsNone(nova.partida.rodada.pergunta)
        sala, partidas = self.partidas(host.sala.codigo)
        self.assertEqual(len(partidas), 2)
        self.assertEqual([len(item[2]) for item in partidas], [10, 10])
        self.assertEqual(sala.status, SalaNemPatoStatus.EM_PARTIDA)

    def test_autorizacao_estados_e_minimo(self):
        host, _ = self.finalizar_primeira()
        with self.assertRaises(Exception) as nao_host:
            self.revanche(host, self.tokens_by_name["Jorge"])
        self.assertEqual(nao_host.exception.status_code, 403)
        with self.assertRaises(Exception) as token:
            self.revanche(host, "inválido")
        self.assertEqual(token.exception.status_code, 401)

        ativa = self.preparar(("A", "B", "C"))
        with self.assertRaises(Exception) as andamento:
            self.revanche(ativa)
        self.assertEqual(andamento.exception.status_code, 409)

        host2, _ = self.finalizar_primeira(("D", "E", "F"))
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host2.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            partida.status = PartidaNemPatoStatus.CANCELADA
            session.commit()
        with self.assertRaises(Exception) as cancelada:
            self.revanche(host2)
        self.assertIn("não permite revanche", cancelada.exception.detail)

        host3, _ = self.finalizar_primeira(("G", "H", "I"))
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host3.sala.codigo))
            jogadores = list(session.scalars(select(JogadorPartidaNemPato).join(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)))
            participantes = list(session.scalars(select(ParticipanteNemPato).where(ParticipanteNemPato.sala_id == sala.id)))
            jogadores[-1].status = ParticipanteNemPatoStatus.ABANDONOU
            participantes[-1].status = ParticipanteNemPatoStatus.ABANDONOU
            session.commit()
        with self.assertRaises(Exception) as poucos:
            self.revanche(host3)
        self.assertIn("3 a 6", poucos.exception.detail)

    def test_exclui_abandonado_compacta_ordem_e_preserva_historico(self):
        host, _ = self.finalizar_primeira(("A", "B", "C", "D"))
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            anterior = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            jogadores = list(session.scalars(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == anterior.id).order_by(JogadorPartidaNemPato.ordem_circular)))
            participante_b = session.get(ParticipanteNemPato, jogadores[1].participante_id)
            jogadores[1].status = ParticipanteNemPatoStatus.ABANDONOU
            participante_b.status = ParticipanteNemPatoStatus.ABANDONOU
            historico = [(j.id, j.nome_snapshot, j.patos) for j in jogadores]
            session.commit()
        nova = self.revanche(host)
        self.assertEqual([j.nome for j in nova.partida.jogadores], ["A", "C", "D"])
        self.assertEqual([j.ordem_circular for j in nova.partida.jogadores], [1, 2, 3])
        sala, partidas = self.partidas(host.sala.codigo)
        self.assertEqual([(j.id, j.nome_snapshot, j.patos) for j in partidas[0][1]], historico)

    def test_perguntas_novas_quando_catalogo_tem_trinta(self):
        host, _ = self.finalizar_primeira(catalogo=30)
        _, antes = self.partidas(host.sala.codigo)
        ids_anteriores = {r.pergunta_id for r in antes[0][2]}
        self.revanche(host)
        _, depois = self.partidas(host.sala.codigo)
        ids_novos = {r.pergunta_id for r in depois[1][2]}
        self.assertEqual(len(ids_novos), 10)
        self.assertTrue(ids_anteriores.isdisjoint(ids_novos))

    def test_revanche_preserva_e_usa_catalogo_privado_da_sala(self):
        host, _ = self.finalizar_primeira(catalogo=30)
        with self.sessions() as session:
            usuario = Usuario(
                nome="Catálogo privado",
                email="privada-revanche@example.com",
                senha_hash="hash",
            )
            session.add(usuario)
            session.flush()
            categoria = Categoria(
                id=uuid4(),
                slug="privada-revanche",
                nome="Privada revanche",
                modo=MODO_NEM_A_PATO,
                origem=ORIGEM_USUARIO,
                usuario_id=usuario.id,
                ativa=True,
            )
            session.add(categoria)
            session.flush()
            perguntas = [
                PerguntaNemPato(
                    categoria_id=categoria.id,
                    enunciado=f"Privada para revanche {indice}",
                    resposta_numerica=indice,
                    explicacao="Não elegível antes da C1.4.",
                    origem=ORIGEM_USUARIO,
                    usuario_id=usuario.id,
                    ativa=True,
                )
                for indice in range(10)
            ]
            session.add_all(perguntas)
            session.flush()
            ids_privados = {pergunta.id for pergunta in perguntas}
            sala = session.scalar(select(SalaNemPato).where(
                SalaNemPato.codigo == host.sala.codigo
            ))
            sala.catalogo_usuario_id = usuario.id
            anterior = session.scalar(select(PartidaNemPato).where(
                PartidaNemPato.sala_id == sala.id
            ))
            anterior.catalogo_usuario_id = usuario.id
            for pergunta in session.scalars(select(PerguntaNemPato).where(
                PerguntaNemPato.origem == "OFICIAL"
            )):
                pergunta.ativa = False
            session.commit()

        self.revanche(host)
        _, partidas = self.partidas(host.sala.codigo)
        ids_revanche = {rodada.pergunta_id for rodada in partidas[1][2]}
        self.assertEqual(ids_privados, ids_revanche)
        self.assertEqual(partidas[1][0].catalogo_usuario_id, usuario.id)


    def test_fallback_com_catalogo_reduzido_reutiliza_so_o_necessario(self):
        host, _ = self.finalizar_primeira(("X", "Y", "Z"), catalogo=15)
        _, antes = self.partidas(host.sala.codigo)
        ids_anteriores = {r.pergunta_id for r in antes[0][2]}
        self.revanche(host)
        _, depois = self.partidas(host.sala.codigo)
        ids_novos = {r.pergunta_id for r in depois[1][2]}
        self.assertEqual(len(ids_novos), 10)
        self.assertEqual(len(ids_novos - ids_anteriores), 5)

    def test_repeticao_natural_rejeita_duplo_clique_e_eu_aponta_nova(self):
        host, _ = self.finalizar_primeira()
        nova = self.revanche(host)
        with self.assertRaises(Exception) as repetida:
            self.revanche(host)
        self.assertEqual(repetida.exception.status_code, 409)
        recuperada = self.recuperar(host)
        self.assertEqual(recuperada.partida.id, nova.partida.id)

        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id).order_by(PartidaNemPato.numero.desc()))
            partida.status = PartidaNemPatoStatus.FINALIZADA
            partida.rodada_atual = 10
            partida.finalizada_em = datetime.now(timezone.utc)
            sala.status = SalaNemPatoStatus.ENCERRADA
            sala.encerrada_em = datetime.now(timezone.utc)
            session.commit()
        terceira = self.revanche(host)
        self.assertEqual(terceira.partida.numero, 3)
        self.assertEqual([j.patos for j in terceira.partida.jogadores], [0, 0, 0])
