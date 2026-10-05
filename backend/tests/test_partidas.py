import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.partidas import avancar_pergunta, criar_partida, enviar_resposta
from app.db.session import get_db
from app.main import app
from app.db.base import Base
from app.db.seed import seed_database
from app.conteudo import (
    CATEGORIAS_OFICIAIS,
    MODO_QUIZ_CLASSICO,
    ORIGEM_USUARIO,
)
from app.models import (
    Categoria,
    Jogador,
    Partida,
    PartidaPergunta,
    Pergunta,
    Resposta,
    Usuario,
)
from app.schemas.partidas import AvancarPergunta, CriarPartida, EnviarResposta, PartidaPublica
from app.services.partidas import PartidasPersistentes


class Relogio:
    def __init__(self):
        self.agora = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.agora


def como_utc(valor):
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)


def seed_catalogo_partidas(session):
    seed_database(session)
    proximo_id = 16
    for categoria_id in ("geral", "tecnologia", "matematica"):
        for numero in range(6, 11):
            session.add(
                Pergunta(
                    id=proximo_id,
                    categoria_id=CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO][categoria_id],
                    enunciado=f"Pergunta {numero} de {categoria_id}",
                    alternativa_a="A",
                    alternativa_b="B",
                    alternativa_c="C",
                    alternativa_d="D",
                    alternativa_correta=0,
                    explicacao="A alternativa A e a correta nesta pergunta de teste.",
                )
            )
            proximo_id += 1
    session.commit()


class TestPartidasPersistentes(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_catalogo_partidas(session)
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

    def test_criacao_persiste_jogador_partida_e_dez_perguntas(self):
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
            self.assertEqual(len(ocorrencias), 10)
            self.assertEqual([item.ordem for item in ocorrencias], list(range(1, 11)))
            self.assertEqual(len({item.pergunta_id for item in ocorrencias}), 10)
            self.assertTrue(
                all(item.pergunta.categoria.slug == "tecnologia" for item in ocorrencias)
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

    def test_convidado_nao_possui_usuario(self):
        criada = self.criar(jogador="Convidado")
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            self.assertEqual(partida.jogador.nome, "Convidado")
            self.assertIsNone(partida.jogador.usuario_id)

    def test_usuario_autenticado_associa_participacoes_e_ignora_nome_enviado(self):
        with self.sessions() as session:
            usuario = Usuario(
                nome="Nome da Conta",
                email="conta@example.com",
                senha_hash="hash",
            )
            session.add(usuario)
            session.commit()
            usuario_id = usuario.id

        partidas_criadas = []
        for _ in range(2):
            with self.sessions() as session:
                usuario = session.get(Usuario, usuario_id)
                criada = self.servico.criar(
                    session,
                    "Nome não confiável",
                    "tecnologia",
                    usuario,
                )
                partidas_criadas.append(criada.partida_id)

        with self.sessions() as session:
            participacoes = list(
                session.scalars(
                    select(Jogador).where(Jogador.usuario_id == usuario_id)
                )
            )
        self.assertEqual(len(participacoes), 2)
        self.assertTrue(all(jogador.nome == "Nome da Conta" for jogador in participacoes))
        self.assertEqual({jogador.usuario_id for jogador in participacoes}, {usuario_id})

    def test_partida_sem_usuario_exige_nome_de_convidado(self):
        with self.assertRaises(HTTPException) as error:
            self.criar(jogador=None)
        self.assertEqual(error.exception.status_code, 422)

    def test_criacao_rejeita_categoria_inexistente_inativa_ou_insuficiente(self):
        with self.assertRaises(HTTPException) as error:
            self.criar("inexistente")
        self.assertEqual(error.exception.status_code, 422)

        with self.sessions() as session:
            session.get(
                Categoria,
                CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"],
            ).ativa = False
            session.commit()
        with self.assertRaises(HTTPException) as error:
            self.criar("tecnologia")
        self.assertEqual(error.exception.status_code, 422)

        with self.sessions() as session:
            categoria_id = CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"]
            session.get(Categoria, categoria_id).ativa = True
            perguntas = list(
                session.scalars(
                    select(Pergunta).where(Pergunta.categoria_id == categoria_id)
                )
            )
            for pergunta in perguntas[2:]:
                pergunta.ativa = False
            session.commit()
        with self.assertRaises(HTTPException) as error:
            self.criar("tecnologia")
        self.assertEqual(error.exception.status_code, 422)

    def test_catalogo_privado_nao_entra_na_criacao_ou_sorteio_publicos(self):
        with self.sessions() as session:
            usuario = Usuario(
                nome="Proprietária",
                email="privada-partida@example.com",
                senha_hash="hash",
            )
            session.add(usuario)
            session.flush()
            categoria_privada = Categoria(
                slug="privada-jogo",
                nome="Privada jogo",
                modo=MODO_QUIZ_CLASSICO,
                origem=ORIGEM_USUARIO,
                usuario_id=usuario.id,
                ativa=True,
            )
            session.add(categoria_privada)
            session.flush()
            for indice in range(10):
                session.add(Pergunta(
                    id=1000 + indice,
                    categoria_id=categoria_privada.id,
                    enunciado=f"Pergunta privada {indice}",
                    alternativa_a="A",
                    alternativa_b="B",
                    alternativa_c="C",
                    alternativa_d="D",
                    alternativa_correta=0,
                    explicacao="Privada.",
                    origem=ORIGEM_USUARIO,
                    usuario_id=usuario.id,
                ))
            session.add(Pergunta(
                id=1100,
                categoria_id=CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"],
                enunciado="Pergunta privada em categoria oficial",
                alternativa_a="A",
                alternativa_b="B",
                alternativa_c="C",
                alternativa_d="D",
                alternativa_correta=0,
                explicacao="Privada.",
                origem=ORIGEM_USUARIO,
                usuario_id=usuario.id,
            ))
            session.commit()

        with self.assertRaises(HTTPException) as error:
            self.criar("privada-jogo")
        self.assertEqual(error.exception.status_code, 422)

        criada = self.criar("tecnologia")
        with self.sessions() as session:
            ids = set(session.scalars(
                select(PartidaPergunta.pergunta_id).where(
                    PartidaPergunta.partida_id == UUID(criada.partida_id)
                )
            ))
        self.assertNotIn(1100, ids)

    def test_nome_vazio_mantem_validacao_do_schema(self):
        with self.assertRaises(ValidationError):
            CriarPartida(jogador="   ", categoria="tecnologia")

    def test_resposta_correta_persiste_pontua_e_aguarda_avanco(self):
        criada = self.criar()
        with self.sessions() as session:
            atual = self.atual(session, criada.partida_id)
            pergunta_id = atual.pergunta_id
            correta = atual.pergunta.alternativa_correta

        self.relogio.agora += timedelta(seconds=2)
        resultado = self.responder(criada.partida_id, pergunta_id, correta)

        self.assertIs(resultado.correta, True)
        self.assertEqual(resultado.alternativa_correta, correta)
        self.assertFalse(resultado.timeout)
        self.assertEqual(resultado.pontos_ganhos, 230)
        self.assertEqual((resultado.pontuacao, resultado.acertos, resultado.erros), (230, 1, 0))
        self.assertIsNone(resultado.pergunta_atual)

        self.assertIsNone(resultado.pergunta_disponibilizada_em)
        with self.sessions() as session:
            self.servico.avancar(session, criada.partida_id, pergunta_id)
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
        self.assertEqual(resultado.alternativa_correta, atual.pergunta.alternativa_correta)
        self.assertEqual(resultado.pontos_ganhos, 0)
        self.assertEqual((resultado.pontuacao, resultado.acertos, resultado.erros), (0, 0, 1))

    def test_deadline_exato_e_depois_sao_timeout_e_ignoram_alternativa(self):
        for seconds in (15, 16):
            with self.subTest(seconds=seconds):
                with self.sessions() as session:
                    Base.metadata.drop_all(session.bind)
                    Base.metadata.create_all(session.bind)
                    seed_catalogo_partidas(session)
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
                with self.sessions() as session:
                    pergunta = session.get(Pergunta, pergunta_id)
                    self.assertEqual(
                        resultado.alternativa_correta,
                        pergunta.alternativa_correta,
                    )
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
                    seed_catalogo_partidas(session)
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

    def test_decima_resposta_finaliza_e_rejeita_nova_resposta(self):
        criada = self.criar()
        resultado = None
        last_question_id = None
        for numero_resposta in range(1, 11):
            with self.sessions() as session:
                atual = self.atual(session, criada.partida_id)
                last_question_id = atual.pergunta_id
                correta = atual.pergunta.alternativa_correta
            resultado = self.responder(criada.partida_id, last_question_id, correta)
            if numero_resposta < 10:
                self.assertEqual(resultado.status, "EM_ANDAMENTO")
                self.assertIsNone(resultado.pergunta_atual)
                with self.sessions() as session:
                    self.servico.avancar(session, criada.partida_id, last_question_id)

        self.assertEqual(resultado.status, "FINALIZADA")
        self.assertIsNotNone(resultado.finalizada_em)
        self.assertIsNone(resultado.pergunta_atual)
        self.assertEqual((resultado.acertos, resultado.erros), (10, 0))
        self.assertEqual(resultado.pontuacao, 2500)
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            self.assertEqual(partida.status, "FINALIZADA")
            self.assertEqual(session.scalar(select(func.count()).select_from(Resposta)), 10)
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
        self.assertIsNone(resultado.pergunta_atual)

    def test_perguntas_operacionais_vem_do_banco(self):
        with self.sessions() as session:
            pergunta = session.get(Pergunta, 6)
            pergunta.enunciado = "Texto exclusivamente persistido"
            for item in session.scalars(
                select(Pergunta).where(
                    Pergunta.categoria_id == CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"],
                    Pergunta.id != 6,
                )
            ):
                item.ativa = False
            session.commit()
        with self.assertRaises(HTTPException):
            self.criar()

        with self.sessions() as session:
            categoria_id = CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"]
            perguntas_tecnologia = list(session.scalars(
                select(Pergunta).where(Pergunta.categoria_id == categoria_id)
            ))
            ids_disponiveis = {item.id for item in perguntas_tecnologia[:10]}
            for item in perguntas_tecnologia:
                item.ativa = item.id in ids_disponiveis
            session.commit()
        criada = self.criar()
        self.assertIn(criada.pergunta_atual.id, ids_disponiveis)
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

    def test_explicacao_persistida_correta_errada_timeout_sem_vazamento(self):
        for modo in ('correta', 'errada', 'timeout'):
            with self.subTest(modo=modo):
                criada = self.criar()
                payload = criada.model_dump_json()
                self.assertNotIn('explicacao', payload)
                self.assertNotIn('alternativa_correta', payload)
                with self.sessions() as session:
                    atual = self.atual(session, criada.partida_id)
                    pergunta_id = atual.pergunta_id
                    correta = atual.alternativa_correta_snapshot
                    explicacao = atual.explicacao_snapshot
                    atual.pergunta.enunciado = f'Pergunta original alterada: {modo}'
                    atual.pergunta.alternativa_a = 'Alternativa original alterada'
                    atual.pergunta.alternativa_correta = (correta + 1) % 4
                    atual.pergunta.explicacao = f'Pergunta original alterada: {modo}'
                    session.commit()
                if modo == 'timeout':
                    self.relogio.agora += timedelta(seconds=16)
                resultado = self.responder(criada.partida_id, pergunta_id,
                    correta if modo == 'correta' else (correta + 1) % 4)
                self.assertEqual(resultado.explicacao, explicacao)
                self.assertEqual(resultado.timeout, modo == 'timeout')
                self.assertEqual(resultado.correta, None if modo == 'timeout' else modo == 'correta')
                self.assertIsNone(resultado.pergunta_atual)
                with self.sessions() as session:
                    proxima = self.servico.avancar(session, criada.partida_id, pergunta_id)
                self.assertNotEqual(proxima.pergunta_atual.id, pergunta_id)
                self.assertEqual(set(proxima.pergunta_atual.model_dump()), {'id', 'pergunta', 'alternativas'})
                self.assertNotIn('explicacao', proxima.model_dump_json())
                self.assertNotIn('alternativa_correta', proxima.model_dump_json())

    def test_leitura_nao_consume_prazo_e_avanco_repetido_nao_renova(self):
        criada = self.criar()
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                self.servico.avancar(session, criada.partida_id, criada.pergunta_atual.id)
        resultado = self.responder(criada.partida_id, criada.pergunta_atual.id, 0)
        self.assertIsNone(resultado.pergunta_disponibilizada_em)
        with self.sessions() as session:
            proxima_id = session.scalar(select(PartidaPergunta.pergunta_id).where(
                PartidaPergunta.partida_id == UUID(criada.partida_id), PartidaPergunta.ordem == 2))
        with self.assertRaises(HTTPException):
            self.responder(criada.partida_id, proxima_id, 0)
        self.relogio.agora += timedelta(minutes=5)
        with self.sessions() as session:
            proxima = self.servico.avancar(session, criada.partida_id, criada.pergunta_atual.id)
        inicio = proxima.pergunta_disponibilizada_em
        self.assertEqual(como_utc(inicio), self.relogio.agora)
        self.relogio.agora += timedelta(seconds=2)
        with self.sessions() as session:
            repetida = self.servico.avancar(session, criada.partida_id, criada.pergunta_atual.id)
        self.assertEqual(como_utc(repetida.pergunta_disponibilizada_em), como_utc(inicio))
        self.assertEqual(proxima.pergunta_atual.id, repetida.pergunta_atual.id)
        self.assertNotIn('explicacao', repetida.model_dump_json())
        resultado2 = self.responder(criada.partida_id, repetida.pergunta_atual.id, 0)
        self.assertFalse(resultado2.timeout)
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                self.servico.avancar(session, criada.partida_id, criada.pergunta_atual.id)


class TestPartidasEndpoints(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        seed_catalogo_partidas(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_funcoes_de_endpoint_preservam_contrato(self):
        created = criar_partida(
            CriarPartida(jogador="Levi", categoria="tecnologia"), self.session, None
        )
        self.assertIsInstance(created, PartidaPublica)
        match = created.model_dump()
        self.assertNotIn("explicacao", match)
        self.assertNotIn("explicacao", match["pergunta_atual"])
        self.assertNotIn("alternativa_correta", match)
        self.assertNotIn("correta", match["pergunta_atual"])
        self.assertNotIn("alternativa_correta", match["pergunta_atual"])

        answered = enviar_resposta(
            match["partida_id"],
            EnviarResposta(
                pergunta_id=match["pergunta_atual"]["id"], alternativa=0
            ),
            self.session,
        )
        self.assertIn("pontos_ganhos", answered.model_dump())
        self.assertIn("alternativa_correta", answered.model_dump())
        pergunta = self.session.get(Pergunta, match["pergunta_atual"]["id"])
        self.assertEqual(answered.explicacao, pergunta.explicacao)
        self.assertIsNone(answered.pergunta_atual)
        proxima = avancar_pergunta(
            match["partida_id"],
            AvancarPergunta(pergunta_id=pergunta.id),
            self.session,
        )
        self.assertNotIn("explicacao", proxima.model_dump_json())
        self.assertNotIn("alternativa_correta", proxima.model_dump_json())


class TestFluxoHttpPartidas(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_catalogo_partidas(session)

        def banco_teste():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = banco_teste
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_fluxo_http_cria_responde_avanca_e_responde_novamente(self):
        criada = self.client.post(
            "/api/v1/partidas",
            json={"jogador": "Integração", "categoria": "tecnologia"},
        )
        self.assertEqual(criada.status_code, 201, criada.text)
        partida = criada.json()
        pergunta_1 = partida["pergunta_atual"]

        respondida = self.client.post(
            f"/api/v1/partidas/{partida['partida_id']}/respostas",
            json={"pergunta_id": pergunta_1["id"], "alternativa": 0},
        )
        self.assertEqual(respondida.status_code, 200, respondida.text)
        feedback = respondida.json()
        self.assertIsNotNone(feedback["explicacao"])
        self.assertIsNone(feedback["pergunta_atual"])

        avancada = self.client.post(
            f"/api/v1/partidas/{partida['partida_id']}/proxima",
            json={"pergunta_id": pergunta_1["id"]},
        )
        self.assertEqual(avancada.status_code, 200, avancada.text)
        proxima = avancada.json()
        pergunta_2 = proxima["pergunta_atual"]
        self.assertNotEqual(pergunta_2["id"], pergunta_1["id"])
        self.assertIsNotNone(proxima["pergunta_disponibilizada_em"])
        self.assertNotIn("explicacao", pergunta_2)
        self.assertNotIn("alternativa_correta", pergunta_2)

        repetida = self.client.post(
            f"/api/v1/partidas/{partida['partida_id']}/proxima",
            json={"pergunta_id": pergunta_1["id"]},
        )
        self.assertEqual(repetida.status_code, 200, repetida.text)
        self.assertEqual(
            datetime.fromisoformat(
                repetida.json()["pergunta_disponibilizada_em"].replace("Z", "+00:00")
            ).replace(tzinfo=None),
            datetime.fromisoformat(
                proxima["pergunta_disponibilizada_em"].replace("Z", "+00:00")
            ).replace(tzinfo=None),
        )

        segunda_resposta = self.client.post(
            f"/api/v1/partidas/{partida['partida_id']}/respostas",
            json={"pergunta_id": pergunta_2["id"], "alternativa": 0},
        )
        self.assertEqual(segunda_resposta.status_code, 200, segunda_resposta.text)
        with self.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Resposta)), 2
            )


if __name__ == "__main__":
    unittest.main()
