from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import event, func, select

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

    def medir_leitura_apos_mutacao(self, acao):
        statements = []
        recuperar_original = self.service._recuperar_apos_mutacao

        def observar(_conn, _cursor, statement, _params, _context, _many):
            statements.append(" ".join(statement.lower().split()))

        def recuperar_instrumentado(*args, **kwargs):
            event.listen(self.engine, "before_cursor_execute", observar)
            try:
                return recuperar_original(*args, **kwargs)
            finally:
                event.remove(self.engine, "before_cursor_execute", observar)

        self.service._recuperar_apos_mutacao = recuperar_instrumentado
        try:
            estado = acao()
        finally:
            self.service._recuperar_apos_mutacao = recuperar_original
        return estado, statements

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
        self.service._timeout_pode_estar_expirado = lambda _db, _codigo: True
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

    def test_polling_sem_timeout_evade_locks_e_reduz_statements(self):
        host, rodada_id = self.preparar_timeout()
        self.definir_deadline(rodada_id, expirado=False)
        statements = []
        sincronizacoes = []
        sincronizar_original = self.service._sincronizar_timeout

        def observar(_conn, _cursor, statement, _params, _context, _many):
            statements.append(" ".join(statement.lower().split()))

        def observar_sincronizacao(*args, **kwargs):
            sincronizacoes.append(True)
            return sincronizar_original(*args, **kwargs)

        self.service._sincronizar_timeout = observar_sincronizacao
        event.listen(self.engine, "before_cursor_execute", observar)
        try:
            estado = self.recuperar(host)
        finally:
            event.remove(self.engine, "before_cursor_execute", observar)
            self.service._sincronizar_timeout = sincronizar_original

        self.assertEqual(estado.partida.rodada.status, "EM_ANDAMENTO")
        self.assertEqual(sincronizacoes, [])
        self.assertFalse(any("for update" in statement for statement in statements))
        # Antes do fast path, uma rodada ativa executava aproximadamente 16
        # statements. O caminho comum agora faz uma sondagem, oito leituras e
        # uma checagem final de versao para impedir snapshots hibridos.
        self.assertEqual(len(statements), 10)

    def test_polling_com_deadline_vencido_revalida_com_locks(self):
        host, rodada_id = self.preparar_timeout()
        self.definir_deadline(rodada_id, expirado=True)
        sincronizacoes = []
        sincronizar_original = self.service._sincronizar_timeout

        def observar_sincronizacao(*args, **kwargs):
            sincronizacoes.append(True)
            return sincronizar_original(*args, **kwargs)

        self.service._sincronizar_timeout = observar_sincronizacao
        try:
            estado = self.recuperar(host)
        finally:
            self.service._sincronizar_timeout = sincronizar_original

        self.assertEqual(sincronizacoes, [True])
        self.assertEqual(estado.partida.rodada.status, "RESULTADO")
        self.assertEqual(estado.partida.rodada.tipo_finalizacao, "SEM_PALPITE")

    def test_tres_mudancas_de_versao_usam_fallback_compartilhado(self):
        host, rodada_id = self.preparar_timeout()
        self.definir_deadline(rodada_id, expirado=False)
        montar_original = self.service._montar_estado_recuperado
        fallback_original = self.service._recuperar_com_lock_compartilhado
        alteracoes = []
        fallbacks = []

        def alterar_depois_da_montagem(*args, **kwargs):
            resultado = montar_original(*args, **kwargs)
            if len(alteracoes) < 3:
                with self.sessions() as concorrente:
                    sala = concorrente.scalar(
                        select(SalaNemPato).where(
                            SalaNemPato.codigo == host.sala.codigo
                        )
                    )
                    sala.estado_versao += 1
                    concorrente.commit()
                    alteracoes.append(sala.estado_versao)
            return resultado

        def observar_fallback(*args, **kwargs):
            fallbacks.append(True)
            return fallback_original(*args, **kwargs)

        self.service._montar_estado_recuperado = alterar_depois_da_montagem
        self.service._recuperar_com_lock_compartilhado = observar_fallback
        try:
            estado = self.recuperar(host)
        finally:
            self.service._montar_estado_recuperado = montar_original
            self.service._recuperar_com_lock_compartilhado = fallback_original

        self.assertEqual(len(alteracoes), 3)
        self.assertEqual(fallbacks, [True])
        self.assertEqual(estado.sala.versao, alteracoes[-1])
        self.assertEqual(estado.partida.rodada.status, "EM_ANDAMENTO")

    def test_leituras_pos_mutacao_reduzem_statements_sem_reusar_orm(self):
        host_inicio = self.preparar(("Inicio-A", "Inicio-B", "Inicio-C"))
        with self.sessions() as session:
            inicio, statements_inicio = self.medir_leitura_apos_mutacao(
                lambda: self.service.iniciar_rodada(
                    session,
                    host_inicio.sala.codigo,
                    host_inicio.credencial_participante,
                )
            )
        self.assertEqual(inicio.partida.rodada.status, "EM_ANDAMENTO")

        host_palpite, rodada_palpite = self.preparar_timeout(
            ("Palpite-A", "Palpite-B", "Palpite-C")
        )
        with self.sessions() as session:
            palpite, statements_palpite = self.medir_leitura_apos_mutacao(
                lambda: self.service.palpitar(
                    session,
                    host_palpite.sala.codigo,
                    rodada_palpite,
                    host_palpite.credencial_participante,
                    10,
                    uuid4(),
                )
            )
        self.assertEqual(palpite.partida.rodada.maior_palpite, 10)

        with self.sessions() as session:
            desafio, statements_desafio = self.medir_leitura_apos_mutacao(
                lambda: self.service.desafiar(
                    session,
                    host_palpite.sala.codigo,
                    rodada_palpite,
                    self.tokens_by_name["Palpite-B"],
                    uuid4(),
                )
            )
        self.assertEqual(desafio.partida.rodada.status, "RESULTADO")

        with self.sessions() as session:
            proxima, statements_proxima = self.medir_leitura_apos_mutacao(
                lambda: self.service.iniciar_proxima_rodada(
                    session,
                    host_palpite.sala.codigo,
                    rodada_palpite,
                    host_palpite.credencial_participante,
                )
            )
        self.assertEqual(proxima.partida.rodada.numero, 2)

        self.assertEqual(len(statements_inicio), 9)
        self.assertEqual(len(statements_palpite), 9)
        self.assertEqual(len(statements_desafio), 8)
        self.assertEqual(len(statements_proxima), 9)
        self.assertFalse(
            any(
                "for update" in statement
                for statements in (
                    statements_inicio,
                    statements_palpite,
                    statements_desafio,
                    statements_proxima,
                )
                for statement in statements
            )
        )

    def test_palpite_revalida_timeout_que_vence_depois_do_commit(self):
        host, rodada_id = self.preparar_timeout()
        recuperar_original = self.service._recuperar_apos_mutacao

        def expirar_antes_da_releitura(*args, **kwargs):
            self.definir_deadline(rodada_id, expirado=True)
            return recuperar_original(*args, **kwargs)

        self.service._recuperar_apos_mutacao = expirar_antes_da_releitura
        try:
            estado = self.palpitar(host, "Levi", rodada_id, 10)
        finally:
            self.service._recuperar_apos_mutacao = recuperar_original

        self.assertEqual(estado.partida.rodada.status, "RESULTADO")
        self.assertEqual(
            estado.partida.rodada.tipo_finalizacao,
            "TEMPO_ESGOTADO",
        )

    def test_releitura_pos_commit_observa_versao_concorrente(self):
        host, rodada_id = self.preparar_timeout(
            ("Versao-A", "Versao-B", "Versao-C")
        )
        self.palpitar(host, "Versao-A", rodada_id, 10)
        antes = self.recuperar(host).sala.versao
        recuperar_original = self.service._recuperar_apos_mutacao

        def alterar_antes_da_releitura(*args, **kwargs):
            with self.sessions() as concorrente:
                sala = concorrente.scalar(
                    select(SalaNemPato).where(
                        SalaNemPato.codigo == host.sala.codigo
                    )
                )
                sala.estado_versao += 10
                concorrente.commit()
            return recuperar_original(*args, **kwargs)

        self.service._recuperar_apos_mutacao = alterar_antes_da_releitura
        try:
            with self.sessions() as session:
                estado = self.service.desafiar(
                    session,
                    host.sala.codigo,
                    rodada_id,
                    self.tokens_by_name["Versao-B"],
                    uuid4(),
                )
        finally:
            self.service._recuperar_apos_mutacao = recuperar_original

        self.assertEqual(estado.sala.versao, antes + 11)
        self.assertEqual(estado.partida.rodada.status, "RESULTADO")

    def test_pos_mutacao_converge_apos_tres_mudancas_concorrentes(self):
        host, rodada_id = self.preparar_timeout(
            ("Fallback-A", "Fallback-B", "Fallback-C")
        )
        self.palpitar(host, "Fallback-A", rodada_id, 10)
        antes = self.recuperar(host).sala.versao
        montar_original = self.service._montar_estado_recuperado
        fallback_original = self.service._recuperar_com_lock_compartilhado
        alteracoes = []
        fallbacks = []

        def alterar_depois_da_montagem(*args, **kwargs):
            resultado = montar_original(*args, **kwargs)
            if len(alteracoes) < 3:
                with self.sessions() as concorrente:
                    sala = concorrente.scalar(
                        select(SalaNemPato).where(
                            SalaNemPato.codigo == host.sala.codigo
                        )
                    )
                    sala.estado_versao += 1
                    concorrente.commit()
                    alteracoes.append(sala.estado_versao)
            return resultado

        def observar_fallback(*args, **kwargs):
            fallbacks.append(True)
            return fallback_original(*args, **kwargs)

        self.service._montar_estado_recuperado = alterar_depois_da_montagem
        self.service._recuperar_com_lock_compartilhado = observar_fallback
        try:
            with self.sessions() as session:
                estado = self.service.desafiar(
                    session,
                    host.sala.codigo,
                    rodada_id,
                    self.tokens_by_name["Fallback-B"],
                    uuid4(),
                )
        finally:
            self.service._montar_estado_recuperado = montar_original
            self.service._recuperar_com_lock_compartilhado = fallback_original

        self.assertEqual(len(alteracoes), 3)
        self.assertEqual(fallbacks, [True])
        self.assertEqual(estado.sala.versao, antes + 4)
        self.assertEqual(estado.partida.rodada.status, "RESULTADO")
        self.assertEqual(estado.partida.rodada.tipo_finalizacao, "DESAFIO")

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
