import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.partidas import criar_partida, enviar_resposta
from app.db.base import Base
from app.db.seed import seed_database
from app.models import Categoria, Jogador, Partida, PartidaPergunta, Pergunta, Resposta
from app.schemas.partidas import CriarPartida, EnviarResposta, PartidaPublica
from app.services.partidas import PartidasPersistentes


class Relogio:
    def __init__(self):
        self.agora = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.agora


def como_utc(valor):
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)


class TestPartidasPersistentes(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_database(session)
        self.relogio = Relogio()
        self.servico = PartidasPersistentes(self.relogio)

    def tearDown(self):
        self.engine.dispose()

    def criar(self, categoria="tecnologia", jogador="Levi"):
        with self.sessions() as session:
            return self.servico.criar(session, jogador, categoria)

    def atual(self, session, partida_id):
        partida_uuid = UUID(partida_id) if isinstance(partida_id, str) else partida_id
        return session.scalar(
            select(PartidaPergunta)
            .where(
                PartidaPergunta.partida_id == partida_uuid,
                PartidaPergunta.disponibilizada_em.is_not(None),
                ~PartidaPergunta.resposta.has(),
            )
            .order_by(PartidaPergunta.ordem)
        )

    def responder(self, partida_id, pergunta_id, alternativa):
        with self.sessions() as session:
            return self.servico.responder(
                session, partida_id, pergunta_id, alternativa
            )

    def test_criacao_persiste_jogador_partida_e_tres_perguntas(self):
        criada = self.criar()
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            ocorrencias = list(
                session.scalars(
                    select(PartidaPergunta)
                    .where(PartidaPergunta.partida_id == partida.id)
                    .order_by(PartidaPergunta.ordem)
                )
            )

            self.assertEqual(session.scalar(select(func.count()).select_from(Jogador)), 1)
            self.assertEqual(partida.status, "EM_ANDAMENTO")
            self.assertEqual(len(ocorrencias), 3)
            self.assertEqual([item.ordem for item in ocorrencias], [1, 2, 3])
            self.assertEqual(len({item.pergunta_id for item in ocorrencias}), 3)
            self.assertTrue(
                all(item.pergunta.categoria_id == "tecnologia" for item in ocorrencias)
            )
            self.assertTrue(all(item.pergunta.ativa for item in ocorrencias))
            self.assertEqual(
                como_utc(ocorrencias[0].disponibilizada_em), self.relogio.agora
            )
            self.assertEqual(
                como_utc(ocorrencias[0].prazo_resposta_em),
                self.relogio.agora + timedelta(seconds=15),
            )
            self.assertTrue(
                all(
                    item.disponibilizada_em is None
                    and item.prazo_resposta_em is None
                    for item in ocorrencias[1:]
                )
            )

        self.assertEqual(criada.status, "EM_ANDAMENTO")
        self.assertNotIn("alternativa_correta", criada.pergunta_atual.model_dump())
        self.assertNotIn("correta", criada.pergunta_atual.model_dump())

    def test_cada_nova_partida_cria_novo_jogador_mesmo_nome(self):
        self.criar(jogador="João")
        self.criar(jogador="João")
        with self.sessions() as session:
            jogadores = list(session.scalars(select(Jogador).where(Jogador.nome == "João")))
        self.assertEqual(len(jogadores), 2)
        self.assertNotEqual(jogadores[0].id, jogadores[1].id)

    def test_criacao_rejeita_categoria_inexistente_inativa_ou_insuficiente(self):
        with self.assertRaises(HTTPException) as error:
            self.criar("inexistente")
        self.assertEqual(error.exception.status_code, 422)

        with self.sessions() as session:
            session.get(Categoria, "tecnologia").ativa = False
            session.commit()
        with self.assertRaises(HTTPException) as error:
            self.criar("tecnologia")
        self.assertEqual(error.exception.status_code, 422)

        with self.sessions() as session:
            session.get(Categoria, "tecnologia").ativa = True
            perguntas = list(
                session.scalars(
                    select(Pergunta).where(Pergunta.categoria_id == "tecnologia")
                )
            )
            for pergunta in perguntas[2:]:
                pergunta.ativa = False
            session.commit()
        with self.assertRaises(HTTPException) as error:
            self.criar("tecnologia")
        self.assertEqual(error.exception.status_code, 422)

    def test_nome_vazio_mantem_validacao_do_schema(self):
        with self.assertRaises(ValidationError):
            CriarPartida(jogador="   ", categoria="tecnologia")

    def test_resposta_correta_persiste_pontua_e_disponibiliza_proxima(self):
        criada = self.criar()
        with self.sessions() as session:
            atual = self.atual(session, criada.partida_id)
            pergunta_id = atual.pergunta_id
            correta = atual.pergunta.alternativa_correta

        self.relogio.agora += timedelta(seconds=2)
        resultado = self.responder(criada.partida_id, pergunta_id, correta)

        self.assertIs(resultado.correta, True)
        self.assertFalse(resultado.timeout)
        self.assertEqual(resultado.pontos_ganhos, 230)
        self.assertEqual((resultado.pontuacao, resultado.acertos, resultado.erros), (230, 1, 0))
        self.assertIsNotNone(resultado.pergunta_atual)
        self.assertNotEqual(resultado.pergunta_atual.id, pergunta_id)

        with self.sessions() as session:
            resposta = session.scalar(select(Resposta))
            partida = session.get(Partida, UUID(criada.partida_id))
            proxima = self.atual(session, criada.partida_id)
            self.assertEqual(resposta.alternativa_selecionada, correta)
            self.assertIs(resposta.correta, True)
            self.assertFalse(resposta.timeout)
            self.assertEqual(resposta.pontos_ganhos, 230)
            self.assertEqual((partida.pontuacao, partida.acertos, partida.erros), (230, 1, 0))
            self.assertEqual(proxima.ordem, 2)
            self.assertEqual(
                como_utc(proxima.disponibilizada_em), self.relogio.agora
            )
            self.assertEqual(
                como_utc(proxima.prazo_resposta_em),
                self.relogio.agora + timedelta(seconds=15),
            )

    def test_resposta_errada_persiste_e_incrementa_apenas_erros(self):
        criada = self.criar()
        with self.sessions() as session:
            atual = self.atual(session, criada.partida_id)
            pergunta_id = atual.pergunta_id
            errada = (atual.pergunta.alternativa_correta + 1) % 4

        resultado = self.responder(criada.partida_id, pergunta_id, errada)
        self.assertIs(resultado.correta, False)
        self.assertEqual(resultado.pontos_ganhos, 0)
        self.assertEqual((resultado.pontuacao, resultado.acertos, resultado.erros), (0, 0, 1))

    def test_deadline_exato_e_depois_sao_timeout_e_ignoram_alternativa(self):
        for seconds in (15, 16):
            with self.subTest(seconds=seconds):
                with self.sessions() as session:
                    Base.metadata.drop_all(session.bind)
                    Base.metadata.create_all(session.bind)
                    seed_database(session)
                self.relogio.agora = datetime(
                    2026, 9, 28, 12, 0, tzinfo=timezone.utc
                )
                criada = self.criar()
                with self.sessions() as session:
                    pergunta_id = self.atual(session, criada.partida_id).pergunta_id
                self.relogio.agora += timedelta(seconds=seconds)
                resultado = self.responder(criada.partida_id, pergunta_id, 3)
                self.assertTrue(resultado.timeout)
                self.assertIsNone(resultado.correta)
                self.assertEqual(resultado.pontos_ganhos, 0)
                self.assertEqual(resultado.erros, 1)
                with self.sessions() as session:
                    resposta = session.scalar(select(Resposta))
                    self.assertIsNone(resposta.alternativa_selecionada)
                    self.assertIsNone(resposta.correta)

    def test_formula_de_tempo_preserva_ceil_e_clamp(self):
        cases = ((0, 250), (0.2, 250), (1.2, 240), (14.2, 110))
        for elapsed, expected in cases:
            with self.subTest(elapsed=elapsed):
                with self.sessions() as session:
                    Base.metadata.drop_all(session.bind)
                    Base.metadata.create_all(session.bind)
                    seed_database(session)
                self.relogio.agora = datetime(
                    2026, 9, 28, 12, 0, tzinfo=timezone.utc
                )
                criada = self.criar()
                with self.sessions() as session:
                    atual = self.atual(session, criada.partida_id)
                    pergunta_id = atual.pergunta_id
                    correta = atual.pergunta.alternativa_correta
                self.relogio.agora += timedelta(seconds=elapsed)
                resultado = self.responder(criada.partida_id, pergunta_id, correta)
                self.assertEqual(resultado.pontos_ganhos, expected)

    def test_pergunta_incorreta_alternativa_invalida_e_partida_inexistente(self):
        criada = self.criar()
        with self.sessions() as session:
            atual = self.atual(session, criada.partida_id)
            pergunta_id = atual.pergunta_id

        with self.assertRaises(HTTPException) as error:
            self.responder(criada.partida_id, -1, 0)
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(HTTPException) as error:
            self.responder(criada.partida_id, pergunta_id, 4)
        self.assertEqual(error.exception.status_code, 422)
        with self.assertRaises(HTTPException) as error:
            self.responder("00000000-0000-0000-0000-000000000000", 1, 0)
        self.assertEqual(error.exception.status_code, 404)

    def test_terceira_resposta_finaliza_e_rejeita_nova_resposta(self):
        criada = self.criar()
        resultado = None
        last_question_id = None
        for _ in range(3):
            with self.sessions() as session:
                atual = self.atual(session, criada.partida_id)
                last_question_id = atual.pergunta_id
                correta = atual.pergunta.alternativa_correta
            resultado = self.responder(criada.partida_id, last_question_id, correta)

        self.assertEqual(resultado.status, "FINALIZADA")
        self.assertIsNotNone(resultado.finalizada_em)
        self.assertIsNone(resultado.pergunta_atual)
        self.assertEqual((resultado.acertos, resultado.erros), (3, 0))
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            self.assertEqual(partida.status, "FINALIZADA")
            self.assertEqual(session.scalar(select(func.count()).select_from(Resposta)), 3)
        with self.assertRaises(HTTPException) as error:
            self.responder(criada.partida_id, last_question_id, 0)
        self.assertEqual(error.exception.status_code, 409)

    def test_nova_session_reconstroi_e_continua_partida(self):
        creation_session = self.sessions()
        criada = self.servico.criar(
            creation_session, "Levi", "tecnologia"
        )
        creation_session.close()

        with self.sessions() as reading_session:
            atual = self.atual(reading_session, criada.partida_id)
            pergunta_id = atual.pergunta_id
            correta = atual.pergunta.alternativa_correta

        response_session = self.sessions()
        resultado = self.servico.responder(
            response_session, criada.partida_id, pergunta_id, correta
        )
        response_session.close()
        self.assertEqual(resultado.acertos, 1)
        self.assertIsNotNone(resultado.pergunta_atual)

    def test_perguntas_operacionais_vem_do_banco(self):
        with self.sessions() as session:
            pergunta = session.get(Pergunta, 6)
            pergunta.enunciado = "Texto exclusivamente persistido"
            for item in session.scalars(
                select(Pergunta).where(
                    Pergunta.categoria_id == "tecnologia", Pergunta.id != 6
                )
            ):
                item.ativa = False
            session.commit()
        with self.assertRaises(HTTPException):
            self.criar()

        with self.sessions() as session:
            for item in session.scalars(
                select(Pergunta).where(Pergunta.categoria_id == "tecnologia")
            ):
                item.ativa = item.id in (6, 7, 8)
            session.commit()
        criada = self.criar()
        self.assertIn(criada.pergunta_atual.id, (6, 7, 8))
        if criada.pergunta_atual.id == 6:
            self.assertEqual(criada.pergunta_atual.pergunta, "Texto exclusivamente persistido")

    def test_estado_persistido_inconsistente_e_rejeitado(self):
        criada = self.criar()
        with self.sessions() as session:
            atual = self.atual(session, criada.partida_id)
            atual.prazo_resposta_em = None
            pergunta_id = atual.pergunta_id
            session.commit()
        with self.assertRaises(HTTPException) as error:
            self.responder(criada.partida_id, pergunta_id, 0)
        self.assertEqual(error.exception.status_code, 409)

    def test_consulta_da_partida_usa_for_update_no_postgresql(self):
        statement = self.servico._consulta_partida_bloqueada(
            UUID("00000000-0000-0000-0000-000000000001")
        )
        compiled = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("FOR UPDATE", compiled)

    def test_integrity_error_retorna_409_e_desfaz_placar_e_resposta(self):
        criada = self.criar()
        with self.sessions() as lookup_session:
            atual = self.atual(lookup_session, criada.partida_id)
            pergunta_id = atual.pergunta_id
            alternativa = atual.pergunta.alternativa_correta

        session = self.sessions()
        with patch.object(
            session,
            "commit",
            side_effect=IntegrityError("commit", {}, Exception("corrida")),
        ):
            with self.assertRaises(HTTPException) as error:
                self.servico.responder(
                    session, criada.partida_id, pergunta_id, alternativa
                )
        session.close()
        self.assertEqual(error.exception.status_code, 409)

        with self.sessions() as verification_session:
            partida = verification_session.get(Partida, UUID(criada.partida_id))
            self.assertEqual((partida.pontuacao, partida.acertos, partida.erros), (0, 0, 0))
            self.assertEqual(
                verification_session.scalar(
                    select(func.count()).select_from(Resposta)
                ),
                0,
            )


class TestPartidasEndpoints(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        seed_database(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_funcoes_de_endpoint_preservam_contrato(self):
        created = criar_partida(
            CriarPartida(jogador="Levi", categoria="tecnologia"), self.session
        )
        self.assertIsInstance(created, PartidaPublica)
        match = created.model_dump()
        self.assertNotIn("correta", match["pergunta_atual"])

        answered = enviar_resposta(
            match["partida_id"],
            EnviarResposta(
                pergunta_id=match["pergunta_atual"]["id"], alternativa=0
            ),
            self.session,
        )
        self.assertIn("pontos_ganhos", answered.model_dump())


if __name__ == "__main__":
    unittest.main()
