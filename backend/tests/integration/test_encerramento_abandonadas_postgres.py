import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import (
    Categoria, Jogador, JogadorPartidaNemPato, PalpiteNemPato,
    ParticipanteNemPato, Partida, PartidaNemPato, PartidaPergunta, Pergunta,
    PerguntaNemPato, Resposta, RodadaNemPato, SalaNemPato, Usuario,
)
from app.nem_a_pato import (
    PartidaNemPatoStatus, ParticipanteNemPatoStatus, RodadaNemPatoStatus,
    SalaNemPatoStatus,
)
from scripts.encerrar_partidas_abandonadas import MaintenanceError, run


URL = os.getenv("ABANDONED_GAMES_TEST_DATABASE_URL", "").strip()
NAME = os.getenv("ABANDONED_GAMES_TEST_DATABASE_NAME", "").strip()


@unittest.skipUnless(URL and NAME, "configure PostgreSQL descartável para encerramento administrativo")
class TestEncerramentoAbandonadasPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(URL)
        if (
            parsed.get_backend_name() != "postgresql"
            or parsed.database != NAME
            or not NAME.startswith("quizhub_abandoned_test_")
            or parsed.port in (None, 5432)
        ):
            raise RuntimeError("exige PostgreSQL descartável fora da porta 5432")
        cls.engine = create_engine(URL, pool_size=6, max_overflow=2, pool_pre_ping=True)
        cls.sessions = sessionmaker(cls.engine, expire_on_commit=False)
        Base.metadata.drop_all(cls.engine)
        Base.metadata.create_all(cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        self.old = datetime.now(timezone.utc) - timedelta(days=10)
        self.recent = datetime.now(timezone.utc) - timedelta(hours=1)

    def _category(self, db, suffix="base"):
        marker = uuid4().hex
        user = Usuario(
            nome="Usuário sintético", email=f"user-{marker}@test.invalid",
            senha_hash="hash-sintetico-nao-utilizado", perfil="JOGADOR",
        )
        db.add(user)
        db.flush()
        category = Categoria(
            id=uuid4(), slug=f"categoria-{suffix}-{marker[:8]}",
            nome=f"Categoria {suffix}", modo="QUIZ_CLASSICO", origem="USUARIO",
            usuario_id=user.id,
        )
        db.add(category)
        db.flush()
        return category

    def _classic(self, db, *, last, answered=True):
        category = self._category(db, "classic")
        player = Jogador(nome="Jogador sintético", visitante_id=uuid4())
        question = Pergunta(
            id=uuid4().int % 1_000_000_000 + 1, categoria_id=category.id,
            enunciado="Pergunta histórica?", alternativa_a="A",
            alternativa_b="B", alternativa_c="C", alternativa_d="D",
            alternativa_correta=0, explicacao="Explicação histórica.", origem="USUARIO",
            usuario_id=category.usuario_id,
        )
        db.add_all([player, question]); db.flush()
        game = Partida(
            jogador_id=player.id, categoria_id=category.id, status="EM_ANDAMENTO",
            pontuacao=130, acertos=1, erros=0, iniciada_em=last,
            categoria_slug_snapshot=category.slug, categoria_nome_snapshot=category.nome,
        )
        db.add(game); db.flush()
        occurrence = PartidaPergunta(
            partida_id=game.id, pergunta_id=question.id, ordem=1,
            disponibilizada_em=last, prazo_resposta_em=last + timedelta(seconds=30),
            categoria_id_snapshot=category.id, categoria_slug_snapshot=category.slug,
            categoria_nome_snapshot=category.nome, enunciado_snapshot=question.enunciado,
            alternativa_a_snapshot="A", alternativa_b_snapshot="B",
            alternativa_c_snapshot="C", alternativa_d_snapshot="D",
            alternativa_correta_snapshot=0, explicacao_snapshot=question.explicacao,
        )
        db.add(occurrence); db.flush()
        if answered:
            db.add(Resposta(
                partida_pergunta_id=occurrence.id, alternativa_selecionada=0,
                correta=True, timeout=False, pontos_ganhos=130, respondida_em=last,
            ))
        db.flush()
        return game

    def _room(self, db, *, last, playing, active_round=False):
        category = self._category(db, "np")
        category.modo = "NEM_A_PATO"
        room = SalaNemPato(
            codigo=f"TEST-{uuid4().hex[:8]}",
            status=SalaNemPatoStatus.EM_PARTIDA if playing else SalaNemPatoStatus.AGUARDANDO,
            criada_em=last,
        )
        db.add(room); db.flush()
        participant = ParticipanteNemPato(
            sala_id=room.id, nome="Participante sintético", token_hash=os.urandom(32),
            ordem_entrada=1, eh_anfitriao=True, status=ParticipanteNemPatoStatus.ATIVO,
            entrou_em=last,
        )
        db.add(participant); db.flush()
        if not playing:
            return room, None, None
        question = PerguntaNemPato(
            categoria_id=category.id, enunciado="Quantos itens?", resposta_numerica=10,
            explicacao="Explicação histórica.", origem="USUARIO", usuario_id=category.usuario_id,
        )
        db.add(question); db.flush()
        game = PartidaNemPato(
            sala_id=room.id, categoria_id=category.id, numero=1,
            status=PartidaNemPatoStatus.EM_ANDAMENTO, rodada_atual=1 if active_round else 0,
            iniciada_em=last,
        )
        db.add(game); db.flush()
        player = JogadorPartidaNemPato(
            partida_id=game.id, participante_id=participant.id,
            nome_snapshot=participant.nome, ordem_circular=1,
            status=ParticipanteNemPatoStatus.ATIVO, criado_em=last,
        )
        db.add(player); db.flush()
        round_ = None
        if active_round:
            round_ = RodadaNemPato(
                partida_id=game.id, pergunta_id=question.id, numero=1,
                status=RodadaNemPatoStatus.EM_ANDAMENTO, jogador_inicial_id=player.id,
                jogador_da_vez_id=player.id, iniciada_em=last,
                termina_em=last + timedelta(seconds=120),
                categoria_id_snapshot=category.id, categoria_slug_snapshot=category.slug,
                categoria_nome_snapshot=category.nome, enunciado_snapshot=question.enunciado,
                resposta_numerica_snapshot=10, explicacao_snapshot=question.explicacao,
            )
            db.add(round_); db.flush()
            db.add(PalpiteNemPato(
                rodada_id=round_.id, jogador_partida_id=player.id, ordem=1,
                valor=9, criado_em=last, client_action_id=uuid4(),
            ))
        db.flush()
        return room, game, round_

    def test_dry_run_nao_muda_registros_e_distingue_recente(self):
        with self.sessions.begin() as db:
            old = self._classic(db, last=self.old)
            recent = self._classic(db, last=self.recent)
        with self.sessions() as db:
            result = run(
                db, classic_ids=[old.id, recent.id], room_ids=[], inactivity_hours=72,
                execute=False, justification="",
            )
            self.assertEqual([item["elegivel"] for item in result["registros"]], [True, False])
            db.rollback()
        with self.sessions() as db:
            self.assertEqual(db.get(Partida, old.id).status, "EM_ANDAMENTO")
            self.assertEqual(db.get(Partida, recent.id).status, "EM_ANDAMENTO")

    def test_execucao_preserva_dados_e_rodada_em_andamento(self):
        with self.sessions.begin() as db:
            classic = self._classic(db, last=self.old)
            waiting, _, _ = self._room(db, last=self.old, playing=False)
            room, game, round_ = self._room(db, last=self.old, playing=True, active_round=True)
            ids = classic.id, waiting.id, room.id, game.id, round_.id
        with self.sessions() as db:
            result = run(
                db, classic_ids=[ids[0]], room_ids=[ids[1], ids[2]], inactivity_hours=72,
                execute=True, justification="Encerramento administrativo de teste",
                confirmed_database=NAME,
            )
            db.commit()
            self.assertTrue(all(item["elegivel"] for item in result["registros"]))
        with self.sessions() as db:
            self.assertEqual(db.get(Partida, ids[0]).status, "EXPIRADA")
            self.assertEqual(db.get(SalaNemPato, ids[1]).status, SalaNemPatoStatus.ENCERRADA)
            self.assertEqual(db.get(SalaNemPato, ids[2]).status, SalaNemPatoStatus.ENCERRADA)
            self.assertEqual(db.get(PartidaNemPato, ids[3]).status, PartidaNemPatoStatus.CANCELADA)
            self.assertEqual(db.get(RodadaNemPato, ids[4]).status, RodadaNemPatoStatus.EM_ANDAMENTO)
            self.assertEqual(db.scalar(select(func.count(Resposta.id))), 1)
            self.assertEqual(db.scalar(select(func.count(PalpiteNemPato.id))), 1)

    def test_selecao_mista_reverte_integralmente(self):
        with self.sessions.begin() as db:
            old = self._classic(db, last=self.old)
            recent = self._classic(db, last=self.recent)
        with self.sessions() as db:
            with self.assertRaises(MaintenanceError):
                run(
                    db, classic_ids=[old.id, recent.id], room_ids=[], inactivity_hours=72,
                    execute=True, justification="Teste de rollback integral",
                    confirmed_database=NAME,
                )
            db.rollback()
        with self.sessions() as db:
            self.assertEqual(db.get(Partida, old.id).status, "EM_ANDAMENTO")

    def test_concorrencia_permite_uma_execucao(self):
        with self.sessions.begin() as db:
            game = self._classic(db, last=self.old)
            game_id = game.id
        barrier = Barrier(2)

        def worker():
            try:
                with self.sessions() as db:
                    barrier.wait(timeout=5)
                    run(
                        db, classic_ids=[game_id], room_ids=[], inactivity_hours=72,
                        execute=True, justification="Teste concorrente controlado",
                        confirmed_database=NAME,
                    )
                    db.commit()
                    return "ok"
            except MaintenanceError:
                return "nao_elegivel"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: worker(), range(2))), ["nao_elegivel", "ok"])
        with self.sessions() as db:
            self.assertEqual(db.get(Partida, game_id).status, "EXPIRADA")


if __name__ == "__main__":
    unittest.main()
