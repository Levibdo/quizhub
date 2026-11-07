import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.partidas import (
    avancar_pergunta,
    criar_partida,
    enviar_resposta,
    recuperar_partida,
)
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
    CatalogoOficial,
    Categoria,
    Jogador,
    Partida,
    PartidaPergunta,
    Pergunta,
    Resposta,
    Temporada,
    Usuario,
)
from app.schemas.partidas import AvancarPergunta, CriarPartida, EnviarResposta, PartidaPublica
from app.security import (
    CLASSIC_GUEST_COOKIE_NAME,
    JWT_COOKIE_NAME,
    criar_token_acesso,
    criar_token_visitante_classico,
)
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
    catalogo = CatalogoOficial(
        catalogo_id="quiz-classico-testes", versao=1,
        modo=MODO_QUIZ_CLASSICO, status="ATIVO", sha256="0" * 64,
    )
    session.add(catalogo)
    session.flush()
    for pergunta in session.scalars(select(Pergunta).where(
        Pergunta.origem == "OFICIAL"
    )):
        pergunta.catalogo_oficial_id = catalogo.id
        pergunta.id_editorial = f"QC-TEST-{pergunta.id}"
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
                    catalogo_oficial_id=catalogo.id,
                    id_editorial=f"QC-TEST-{proximo_id}",
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
        self.visitante_id = uuid4()

    def tearDown(self):
        self.engine.dispose()

    def criar(self, categoria="tecnologia", jogador="Levi"):
        with self.sessions() as session:
            return self.servico.criar(
                session, jogador, categoria, visitante_id=self.visitante_id
            )

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
                session,
                partida_id,
                pergunta_id,
                alternativa,
                None,
                self.visitante_id,
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
            self.assertIsNotNone(partida.temporada_id)
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

    def test_criacao_falha_sem_temporada_ativa(self):
        with self.sessions() as session:
            temporada = session.scalar(select(Temporada).where(
                Temporada.status == "ATIVA"
            ))
            temporada.status = "ENCERRADA"
            temporada.encerra_em = max(
                self.relogio.agora,
                temporada.inicia_em.replace(tzinfo=timezone.utc),
            )
            session.commit()
        with self.assertRaises(HTTPException) as contexto:
            self.criar()
        self.assertEqual(contexto.exception.status_code, 503)
        with self.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Partida)), 0)

    def test_temporada_atribuida_na_criacao_e_preservada_ao_finalizar(self):
        criada = self.criar()
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            temporada_original = partida.temporada_id
        for _ in range(10):
            with self.sessions() as session:
                atual = self.atual(session, UUID(criada.partida_id))
                pergunta_id = atual.pergunta_id
            resposta = self.responder(criada.partida_id, pergunta_id, 0)
            if resposta.status == "EM_ANDAMENTO":
                with self.sessions() as session:
                    self.servico.avancar(
                        session, criada.partida_id, pergunta_id, None, self.visitante_id
                    )
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            self.assertEqual(partida.status, "FINALIZADA")
            self.assertEqual(partida.temporada_id, temporada_original)

    def test_criacao_visitante_persiste_identidade_opcional(self):
        visitante_id = uuid4()
        with self.sessions() as session:
            criada = self.servico.criar(
                session,
                "Visitante",
                "tecnologia",
                visitante_id=visitante_id,
            )
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            self.assertEqual(partida.jogador.visitante_id, visitante_id)
            self.assertIsNone(partida.jogador.usuario_id)

    def test_criacao_sem_identidade_preserva_visitante_historico(self):
        with self.sessions() as session:
            criada = self.servico.criar(
                session, "Visitante legado", "tecnologia"
            )
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            self.assertIsNone(partida.jogador.visitante_id)
            self.assertIsNone(partida.jogador.usuario_id)

    def test_usuario_autenticado_ignora_identidade_de_visitante(self):
        visitante_id = uuid4()
        with self.sessions() as session:
            usuario = Usuario(
                nome="Usuária",
                email="usuario-ranking@example.com",
                senha_hash="hash-de-teste",
            )
            session.add(usuario)
            session.commit()
            criada = self.servico.criar(
                session,
                None,
                "tecnologia",
                usuario,
                visitante_id=visitante_id,
            )
            partida = session.get(Partida, UUID(criada.partida_id))
            self.assertEqual(partida.jogador.usuario_id, usuario.id)
            self.assertIsNone(partida.jogador.visitante_id)

    def test_schema_ignora_identidade_de_visitante_controlada_pelo_cliente(self):
        entrada = CriarPartida(
            jogador="Visitante",
            categoria="tecnologia",
            visitante_id=str(uuid4()),
        )
        self.assertNotIn("visitante_id", entrada.model_dump())

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
            self.servico.avancar(
                session, criada.partida_id, pergunta_id, None, self.visitante_id
            )
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
                    self.servico.avancar(
                        session,
                        criada.partida_id,
                        last_question_id,
                        None,
                        self.visitante_id,
                    )

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
            creation_session,
            "Levi",
            "tecnologia",
            visitante_id=self.visitante_id,
        )
        creation_session.close()

        with self.sessions() as reading_session:
            atual = self.atual(reading_session, criada.partida_id)
            pergunta_id = atual.pergunta_id
            correta = atual.pergunta.alternativa_correta

        response_session = self.sessions()
        resultado = self.servico.responder(
            response_session,
            criada.partida_id,
            pergunta_id,
            correta,
            None,
            self.visitante_id,
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
                    session,
                    criada.partida_id,
                    pergunta_id,
                    alternativa,
                    None,
                    self.visitante_id,
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
                    proxima = self.servico.avancar(
                        session,
                        criada.partida_id,
                        pergunta_id,
                        None,
                        self.visitante_id,
                    )
                self.assertNotEqual(proxima.pergunta_atual.id, pergunta_id)
                self.assertEqual(set(proxima.pergunta_atual.model_dump()), {'id', 'pergunta', 'alternativas'})
                self.assertNotIn('explicacao', proxima.model_dump_json())
                self.assertNotIn('alternativa_correta', proxima.model_dump_json())

    def test_leitura_nao_consume_prazo_e_avanco_repetido_nao_renova(self):
        criada = self.criar()
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                self.servico.avancar(
                    session,
                    criada.partida_id,
                    criada.pergunta_atual.id,
                    None,
                    self.visitante_id,
                )
        resultado = self.responder(criada.partida_id, criada.pergunta_atual.id, 0)
        self.assertIsNone(resultado.pergunta_disponibilizada_em)
        with self.sessions() as session:
            proxima_id = session.scalar(select(PartidaPergunta.pergunta_id).where(
                PartidaPergunta.partida_id == UUID(criada.partida_id), PartidaPergunta.ordem == 2))
        with self.assertRaises(HTTPException):
            self.responder(criada.partida_id, proxima_id, 0)
        self.relogio.agora += timedelta(minutes=5)
        with self.sessions() as session:
            proxima = self.servico.avancar(
                session,
                criada.partida_id,
                criada.pergunta_atual.id,
                None,
                self.visitante_id,
            )
        inicio = proxima.pergunta_disponibilizada_em
        self.assertEqual(como_utc(inicio), self.relogio.agora)
        self.relogio.agora += timedelta(seconds=2)
        with self.sessions() as session:
            repetida = self.servico.avancar(
                session,
                criada.partida_id,
                criada.pergunta_atual.id,
                None,
                self.visitante_id,
            )
        self.assertEqual(como_utc(repetida.pergunta_disponibilizada_em), como_utc(inicio))
        self.assertEqual(proxima.pergunta_atual.id, repetida.pergunta_atual.id)
        self.assertNotIn('explicacao', repetida.model_dump_json())
        resultado2 = self.responder(criada.partida_id, repetida.pergunta_atual.id, 0)
        self.assertFalse(resultado2.timeout)
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                self.servico.avancar(
                    session,
                    criada.partida_id,
                    criada.pergunta_atual.id,
                    None,
                    self.visitante_id,
                )

    def test_recuperacao_preserva_sequencia_prazo_e_nao_escreve(self):
        criada = self.criar()
        with self.sessions() as session:
            partida_antes = session.execute(select(
                Partida.status,
                Partida.pontuacao,
                Partida.acertos,
                Partida.erros,
                Partida.finalizada_em,
            ).where(Partida.id == UUID(criada.partida_id))).one()
            respostas_antes = session.scalar(
                select(func.count()).select_from(Resposta)
            )
            antes = list(session.execute(
                select(
                    PartidaPergunta.id,
                    PartidaPergunta.pergunta_id,
                    PartidaPergunta.ordem,
                    PartidaPergunta.disponibilizada_em,
                    PartidaPergunta.prazo_resposta_em,
                )
                .where(PartidaPergunta.partida_id == UUID(criada.partida_id))
                .order_by(PartidaPergunta.ordem)
            ))
            recuperada = self.servico.recuperar(
                session, criada.partida_id, None, self.visitante_id
            )
            depois = list(session.execute(
                select(
                    PartidaPergunta.id,
                    PartidaPergunta.pergunta_id,
                    PartidaPergunta.ordem,
                    PartidaPergunta.disponibilizada_em,
                    PartidaPergunta.prazo_resposta_em,
                )
                .where(PartidaPergunta.partida_id == UUID(criada.partida_id))
                .order_by(PartidaPergunta.ordem)
            ))
            partida_depois = session.execute(select(
                Partida.status,
                Partida.pontuacao,
                Partida.acertos,
                Partida.erros,
                Partida.finalizada_em,
            ).where(Partida.id == UUID(criada.partida_id))).one()
            respostas_depois = session.scalar(
                select(func.count()).select_from(Resposta)
            )
        self.assertEqual(recuperada.fase, "AGUARDANDO_RESPOSTA")
        self.assertEqual(recuperada.ordem_atual, 1)
        self.assertEqual(recuperada.total_perguntas, 10)
        self.assertEqual(recuperada.pergunta_atual.id, criada.pergunta_atual.id)
        self.assertEqual(
            como_utc(recuperada.prazo_resposta_em),
            como_utc(criada.prazo_resposta_em),
        )
        self.assertEqual(antes, depois)
        self.assertEqual(partida_antes, partida_depois)
        self.assertEqual(respostas_antes, respostas_depois)

    def test_recuperacao_devolve_feedback_sem_revelar_proxima_pergunta(self):
        criada = self.criar()
        resultado = self.responder(
            criada.partida_id, criada.pergunta_atual.id, 0
        )
        with self.sessions() as session:
            recuperada = self.servico.recuperar(
                session, criada.partida_id, None, self.visitante_id
            )
        self.assertEqual(recuperada.fase, "AGUARDANDO_AVANCO")
        self.assertEqual(recuperada.pergunta_atual.id, criada.pergunta_atual.id)
        self.assertEqual(
            recuperada.resultado_ultima_resposta.pergunta_id,
            criada.pergunta_atual.id,
        )
        self.assertEqual(
            recuperada.resultado_ultima_resposta.alternativa_correta,
            resultado.alternativa_correta,
        )

    def test_propriedade_centralizada_protege_leitura_resposta_e_avanco(self):
        criada = self.criar()
        outra_identidade = uuid4()
        operacoes = (
            lambda session: self.servico.recuperar(
                session, criada.partida_id, None, outra_identidade
            ),
            lambda session: self.servico.responder(
                session,
                criada.partida_id,
                criada.pergunta_atual.id,
                0,
                None,
                outra_identidade,
            ),
            lambda session: self.servico.avancar(
                session,
                criada.partida_id,
                criada.pergunta_atual.id,
                None,
                outra_identidade,
            ),
        )
        for operacao in operacoes:
            with self.subTest(operacao=operacao):
                with self.sessions() as session, self.assertRaises(HTTPException) as erro:
                    operacao(session)
                self.assertEqual(erro.exception.status_code, 404)

    def test_partida_concluida_e_legado_sem_identidade_tem_estado_seguro(self):
        criada = self.criar()
        with self.sessions() as session:
            partida = session.get(Partida, UUID(criada.partida_id))
            partida.status = "FINALIZADA"
            partida.finalizada_em = self.relogio.agora
            session.commit()
        with self.sessions() as session:
            recuperada = self.servico.recuperar(
                session, criada.partida_id, None, self.visitante_id
            )
        self.assertEqual(recuperada.fase, "FINALIZADA")
        self.assertIsNone(recuperada.pergunta_atual)

        with self.sessions() as session:
            legada = self.servico.criar(session, "Legado", "tecnologia")
            with self.assertRaises(HTTPException) as erro:
                self.servico.recuperar(
                    session, legada.partida_id, None, self.visitante_id
                )
        self.assertEqual(erro.exception.status_code, 404)


class TestPartidasEndpoints(unittest.TestCase):
    def setUp(self):
        self.jwt_env = patch.dict(
            "os.environ", {"JWT_SECRET": "segredo-de-teste-partidas-com-mais-de-32-bytes"}
        )
        self.jwt_env.start()
        self.addCleanup(self.jwt_env.stop)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        seed_catalogo_partidas(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_funcoes_de_endpoint_preservam_contrato(self):
        token_visitante = criar_token_visitante_classico(uuid4())
        created = criar_partida(
            CriarPartida(jogador="Levi", categoria="tecnologia"),
            Response(),
            self.session,
            None,
            token_visitante,
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
            None,
            token_visitante,
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
            None,
            token_visitante,
        )
        self.assertNotIn("explicacao", proxima.model_dump_json())
        self.assertNotIn("alternativa_correta", proxima.model_dump_json())

        recuperada = recuperar_partida(
            match["partida_id"], self.session, None, token_visitante
        )
        self.assertEqual(recuperada.fase, "AGUARDANDO_RESPOSTA")
        self.assertEqual(recuperada.ordem_atual, 2)


class TestFluxoHttpPartidas(unittest.TestCase):
    def setUp(self):
        self.jwt_env = patch.dict(
            "os.environ", {"JWT_SECRET": "segredo-de-teste-partidas-http-com-mais-de-32-bytes"}
        )
        self.jwt_env.start()
        self.addCleanup(self.jwt_env.stop)
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
        self.origem = {"Origin": "http://testserver"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_fluxo_http_cria_responde_avanca_e_responde_novamente(self):
        criada = self.client.post(
            "/api/v1/partidas",
            json={"jogador": "Integração", "categoria": "tecnologia"},
            headers=self.origem,
        )
        self.assertEqual(criada.status_code, 201, criada.text)
        partida = criada.json()
        pergunta_1 = partida["pergunta_atual"]

        respondida = self.client.post(
            f"/api/v1/partidas/{partida['partida_id']}/respostas",
            json={"pergunta_id": pergunta_1["id"], "alternativa": 0},
            headers=self.origem,
        )
        self.assertEqual(respondida.status_code, 200, respondida.text)
        feedback = respondida.json()
        self.assertIsNotNone(feedback["explicacao"])
        self.assertIsNone(feedback["pergunta_atual"])

        avancada = self.client.post(
            f"/api/v1/partidas/{partida['partida_id']}/proxima",
            json={"pergunta_id": pergunta_1["id"]},
            headers=self.origem,
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
            headers=self.origem,
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
            headers=self.origem,
        )
        self.assertEqual(segunda_resposta.status_code, 200, segunda_resposta.text)
        with self.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Resposta)), 2
            )

    def test_http_recupera_feedback_e_isola_identidade_convidada(self):
        criada = self.client.post(
            "/api/v1/partidas",
            json={
                "jogador": "Visitante seguro",
                "categoria": "tecnologia",
                "visitante_id": str(uuid4()),
            },
            headers=self.origem,
        )
        self.assertEqual(criada.status_code, 201, criada.text)
        partida = criada.json()
        self.assertIn("quizhub_classic_guest", criada.cookies)

        primeira = self.client.get(f"/api/v1/partidas/{partida['partida_id']}")
        self.assertEqual(primeira.status_code, 200, primeira.text)
        self.assertEqual(primeira.json()["fase"], "AGUARDANDO_RESPOSTA")

        resposta = self.client.post(
            f"/api/v1/partidas/{partida['partida_id']}/respostas",
            json={"pergunta_id": partida["pergunta_atual"]["id"], "alternativa": 0},
            headers=self.origem,
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        feedback = self.client.get(f"/api/v1/partidas/{partida['partida_id']}")
        self.assertEqual(feedback.status_code, 200, feedback.text)
        self.assertEqual(feedback.json()["fase"], "AGUARDANDO_AVANCO")
        self.assertIsNotNone(feedback.json()["resultado_ultima_resposta"])

        sem_identidade = TestClient(app)
        try:
            anonima = sem_identidade.get(
                f"/api/v1/partidas/{partida['partida_id']}"
            )
            self.assertEqual(anonima.status_code, 401)
            outra = sem_identidade.post(
                "/api/v1/partidas",
                json={"jogador": "Outro", "categoria": "tecnologia"},
                headers=self.origem,
            )
            self.assertEqual(outra.status_code, 201, outra.text)
            alheia = sem_identidade.get(
                f"/api/v1/partidas/{partida['partida_id']}"
            )
            self.assertEqual(alheia.status_code, 404)
        finally:
            sem_identidade.close()

    def test_origem_e_obrigatoria_nos_tres_posts_classicos(self):
        total_inicial = 0
        for headers in ({}, {"Origin": "https://origem-invalida.example"}):
            resposta = self.client.post(
                "/api/v1/partidas",
                json={"jogador": "CSRF", "categoria": "tecnologia"},
                headers=headers,
            )
            self.assertEqual(resposta.status_code, 403, resposta.text)
        with self.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Partida)),
                total_inicial,
            )

        criada = self.client.post(
            "/api/v1/partidas",
            json={"jogador": "CSRF", "categoria": "tecnologia"},
            headers=self.origem,
        ).json()
        rota_resposta = f"/api/v1/partidas/{criada['partida_id']}/respostas"
        payload_resposta = {
            "pergunta_id": criada["pergunta_atual"]["id"], "alternativa": 0
        }
        for headers in ({}, {"Origin": "https://origem-invalida.example"}):
            resposta = self.client.post(
                rota_resposta, json=payload_resposta, headers=headers
            )
            self.assertEqual(resposta.status_code, 403, resposta.text)

        respondida = self.client.post(
            rota_resposta, json=payload_resposta, headers=self.origem
        )
        self.assertEqual(respondida.status_code, 200, respondida.text)
        rota_avanco = f"/api/v1/partidas/{criada['partida_id']}/proxima"
        payload_avanco = {"pergunta_id": criada["pergunta_atual"]["id"]}
        for headers in ({}, {"Origin": "https://origem-invalida.example"}):
            resposta = self.client.post(
                rota_avanco, json=payload_avanco, headers=headers
            )
            self.assertEqual(resposta.status_code, 403, resposta.text)
        avancada = self.client.post(
            rota_avanco, json=payload_avanco, headers=self.origem
        )
        self.assertEqual(avancada.status_code, 200, avancada.text)

    def test_cookie_visitante_tem_atributos_de_seguranca_completos(self):
        with patch.dict("os.environ", {"JWT_COOKIE_SECURE": "true"}):
            resposta = self.client.post(
                "/api/v1/partidas",
                json={"jogador": "Cookie", "categoria": "tecnologia"},
                headers=self.origem,
            )
        self.assertEqual(resposta.status_code, 201, resposta.text)
        cookie = resposta.headers["set-cookie"].lower()
        self.assertIn(f"{CLASSIC_GUEST_COOKIE_NAME}=", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("path=/api/v1/partidas", cookie)
        self.assertIn("max-age=2592000", cookie)

    def test_tokens_visitantes_invalidos_expirados_e_de_tipo_errado_sao_rejeitados(self):
        criada = self.client.post(
            "/api/v1/partidas",
            json={"jogador": "Token", "categoria": "tecnologia"},
            headers=self.origem,
        ).json()
        rota = f"/api/v1/partidas/{criada['partida_id']}"
        emitido = datetime.now(timezone.utc) - timedelta(hours=2)
        tokens = (
            criar_token_visitante_classico(
                uuid4(), agora=emitido, duracao=timedelta(hours=1)
            ),
            criar_token_visitante_classico(uuid4()) + "adulterado",
            criar_token_acesso(uuid4()),
        )
        for token in tokens:
            with self.subTest(token=token[-8:]):
                cliente = TestClient(app)
                try:
                    cliente.cookies.set(CLASSIC_GUEST_COOKIE_NAME, token)
                    resposta = cliente.get(rota)
                    self.assertEqual(resposta.status_code, 401, resposta.text)
                finally:
                    cliente.close()

    def test_usuario_autenticado_nao_acessa_partida_de_outro_e_sessao_inativa_expira(self):
        with self.sessions() as session:
            usuario_a = Usuario(
                nome="Usuário A", email="a-propriedade@example.com", senha_hash="hash"
            )
            usuario_b = Usuario(
                nome="Usuário B", email="b-propriedade@example.com", senha_hash="hash"
            )
            session.add_all((usuario_a, usuario_b))
            session.commit()
            usuario_a_id, usuario_b_id = usuario_a.id, usuario_b.id
        cliente_a, cliente_b = TestClient(app), TestClient(app)
        try:
            cliente_a.cookies.set(JWT_COOKIE_NAME, criar_token_acesso(usuario_a_id))
            cliente_b.cookies.set(JWT_COOKIE_NAME, criar_token_acesso(usuario_b_id))
            criada = cliente_a.post(
                "/api/v1/partidas",
                json={"categoria": "tecnologia"},
                headers=self.origem,
            )
            self.assertEqual(criada.status_code, 201, criada.text)
            partida = criada.json()
            rota = f"/api/v1/partidas/{partida['partida_id']}"
            self.assertEqual(cliente_a.get(rota).status_code, 200)
            self.assertEqual(cliente_b.get(rota).status_code, 404)
            self.assertEqual(cliente_b.post(
                f"{rota}/respostas",
                json={"pergunta_id": partida["pergunta_atual"]["id"], "alternativa": 0},
                headers=self.origem,
            ).status_code, 404)
            self.assertEqual(cliente_b.post(
                f"{rota}/proxima",
                json={"pergunta_id": partida["pergunta_atual"]["id"]},
                headers=self.origem,
            ).status_code, 404)

            with self.sessions() as session:
                session.get(Usuario, usuario_a_id).ativo = False
                session.commit()
            self.assertEqual(cliente_a.get(rota).status_code, 401)
        finally:
            cliente_a.close()
            cliente_b.close()

    def test_sessao_autenticada_expirada_nao_recupera_partida_historica(self):
        with self.sessions() as session:
            usuario = Usuario(
                nome="Histórico", email="historico-auth@example.com", senha_hash="hash"
            )
            session.add(usuario)
            session.commit()
            usuario_id = usuario.id
            criada = PartidasPersistentes().criar(
                session, None, "tecnologia", usuario
            )
        rota = f"/api/v1/partidas/{criada.partida_id}"
        cliente = TestClient(app)
        try:
            cliente.cookies.set(JWT_COOKIE_NAME, criar_token_acesso(usuario_id))
            self.assertEqual(cliente.get(rota).status_code, 200)
            cliente.cookies.set(JWT_COOKIE_NAME, criar_token_acesso(
                usuario_id,
                agora=datetime.now(timezone.utc) - timedelta(hours=2),
                duracao=timedelta(hours=1),
            ))
            self.assertEqual(cliente.get(rota).status_code, 401)
        finally:
            cliente.close()


if __name__ == "__main__":
    unittest.main()
