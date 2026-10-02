import hashlib
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import ParticipanteNemPato, SalaNemPato
from app.nem_a_pato import ParticipanteNemPatoStatus, SalaNemPatoStatus
from app.services.salas_nem_a_pato import (
	ALFABETO_CODIGO_SALA,
	HEADER_TOKEN_NEM_PATO,
	SalasNemAPatoService,
)


class SalasNemAPatoTestCase(unittest.TestCase):
	def setUp(self):
		self.engine = create_engine(
			"sqlite://",
			connect_args={"check_same_thread": False},
			poolclass=StaticPool,
		)
		Base.metadata.create_all(self.engine)
		self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
		self.codigo_counter = 0
		self.token_counter = 0
		self.service = SalasNemAPatoService(
			gerador_codigo=self._codigo,
			gerador_credencial=self._token,
		)

	def tearDown(self):
		app.dependency_overrides.clear()
		self.engine.dispose()

	def _codigo(self):
		self.codigo_counter += 1
		return "NPABCD" if self.codigo_counter == 1 else f"NPABC{chr(67 + self.codigo_counter)}"

	def _token(self):
		self.token_counter += 1
		return f"token-de-teste-{self.token_counter}"

	def criar(self, nome="Levi"):
		with self.sessions() as session:
			return self.service.criar(session, nome)

	def entrar(self, codigo, nome):
		with self.sessions() as session:
			return self.service.entrar(session, codigo, nome)

	def participante(self, participante_id):
		with self.sessions() as session:
			return session.get(ParticipanteNemPato, participante_id)

	def sala_db(self, codigo):
		with self.sessions() as session:
			return session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))

	def client(self):
		def db_override():
			with self.sessions() as session:
				yield session

		app.dependency_overrides[get_db] = db_override
		return TestClient(app)


class TestLobbyNemAPatoService(SalasNemAPatoTestCase):
	def test_criar_sala_host_ordem_token_hash_e_versao_inicial(self):
		criado = self.criar("  Levi  ")
		self.assertEqual(criado.sala.codigo, "NPABCD")
		self.assertEqual(criado.sala.status, "AGUARDANDO")
		self.assertEqual(criado.sala.versao, 0)
		self.assertEqual(criado.participante.nome, "Levi")
		self.assertEqual(criado.participante.ordem_entrada, 1)
		self.assertTrue(criado.participante.eh_anfitriao)
		self.assertTrue(criado.credencial_participante)
		self.assertEqual(set(criado.sala.model_dump()), {
			"codigo", "status", "versao", "criada_em", "participantes",
			"participantes_ativos", "limite_jogadores",
		})
		with self.sessions() as session:
			participante = session.get(ParticipanteNemPato, criado.participante.id)
			self.assertEqual(
				participante.token_hash,
				hashlib.sha256(criado.credencial_participante.encode()).digest(),
			)
			self.assertNotEqual(participante.token_hash, criado.credencial_participante.encode())

	def test_codigo_curto_usa_alfabeto_nao_ambiguo(self):
		criado = self.criar()
		self.assertEqual(len(criado.sala.codigo), 6)
		self.assertTrue(criado.sala.codigo.isupper())
		self.assertTrue(set(criado.sala.codigo).issubset(set(ALFABETO_CODIGO_SALA)))

	def test_colisao_de_codigo_reexecuta_com_limite(self):
		self.criar()
		valores = iter(("NPABCD", "NPABCE"))
		service = SalasNemAPatoService(
			gerador_codigo=lambda: next(valores),
			gerador_credencial=lambda: "outro-token",
			tentativas_codigo=2,
		)
		with self.sessions() as session:
			criada = service.criar(session, "Jorge")
		self.assertEqual(criada.sala.codigo, "NPABCE")

	def test_colisao_excedendo_tentativas_retorna_503(self):
		self.criar()
		service = SalasNemAPatoService(
			gerador_codigo=lambda: "NPABCD",
			gerador_credencial=lambda: "nunca-usado",
			tentativas_codigo=2,
		)
		with self.sessions() as session:
			with self.assertRaises(Exception) as erro:
				service.criar(session, "Jorge")
		self.assertEqual(erro.exception.status_code, 503)

	def test_ordem_incrementa_e_nao_reutiliza_ordem_de_abandono(self):
		sala = self.criar()
		segundo = self.entrar(sala.sala.codigo, "Jorge")
		terceiro = self.entrar(sala.sala.codigo, "Luana")
		with self.sessions() as session:
			self.service.abandonar(
				session, sala.sala.codigo, segundo.credencial_participante
			)
		quarto = self.entrar(sala.sala.codigo, "Leone")
		self.assertEqual(
			[sala.participante.ordem_entrada, segundo.participante.ordem_entrada,
			 terceiro.participante.ordem_entrada, quarto.participante.ordem_entrada],
			[1, 2, 3, 4],
		)

	def test_lobby_limita_seis_ativos_e_abandonado_nao_conta(self):
		sala = self.criar()
		participantes = [self.entrar(sala.sala.codigo, f"Jogador {i}") for i in range(2, 7)]
		with self.sessions() as session:
			with self.assertRaises(Exception) as erro:
				self.service.entrar(session, sala.sala.codigo, "Sétimo")
		self.assertEqual(erro.exception.status_code, 409)
		with self.sessions() as session:
			self.service.abandonar(
				session, sala.sala.codigo, participantes[1].credencial_participante
			)
		novo = self.entrar(sala.sala.codigo, "Novo")
		self.assertEqual(novo.participante.ordem_entrada, 7)
		self.assertEqual(novo.sala.participantes_ativos, 6)

	def test_nome_trim_unico_case_insensitive(self):
		sala = self.criar("Levi")
		with self.sessions() as session:
			with self.assertRaises(Exception) as erro:
				self.service.entrar(session, sala.sala.codigo, "  lEVI ")
		self.assertEqual(erro.exception.status_code, 409)
		outra = self.entrar(sala.sala.codigo, "  Jorge  ")
		self.assertEqual(outra.participante.nome, "Jorge")

	def test_nome_de_participante_abandonado_permanece_reservado(self):
		sala = self.criar()
		jogador = self.entrar(sala.sala.codigo, "Jorge")
		with self.sessions() as session:
			self.service.abandonar(
				session, sala.sala.codigo, jogador.credencial_participante
			)
		with self.sessions() as session:
			with self.assertRaises(Exception) as erro:
				self.service.entrar(session, sala.sala.codigo, " JORGE ")
		self.assertEqual(erro.exception.status_code, 409)

	def test_nome_vazio_e_longo_rejeitado(self):
		for nome in ("  ", "x" * 101):
			with self.subTest(nome=nome[:5]), self.sessions() as session:
				with self.assertRaises(Exception) as erro:
					self.service.criar(session, nome)
				self.assertEqual(erro.exception.status_code, 422)

	def test_sala_inexistente_e_nao_aguardando(self):
		with self.sessions() as session:
			with self.assertRaises(Exception) as ausente:
				self.service.entrar(session, "ZZZZZZ", "Jorge")
		self.assertEqual(ausente.exception.status_code, 404)
		criada = self.criar()
		with self.sessions() as session:
			sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == criada.sala.codigo))
			sala.status = SalaNemPatoStatus.ENCERRADA
			session.commit()
		with self.sessions() as session:
			with self.assertRaises(Exception) as fechada:
				self.service.entrar(session, criada.sala.codigo, "Jorge")
		self.assertEqual(fechada.exception.status_code, 409)

	def test_transferencia_host_para_ativo_de_menor_ordem(self):
		sala = self.criar()
		segundo = self.entrar(sala.sala.codigo, "Jorge")
		terceiro = self.entrar(sala.sala.codigo, "Luana")
		with self.sessions() as session:
			resultado = self.service.abandonar(
				session, sala.sala.codigo, sala.credencial_participante
			)
		self.assertFalse(any(p.eh_anfitriao and p.id == sala.participante.id for p in resultado.participantes))
		novo_host = next(p for p in resultado.participantes if p.eh_anfitriao)
		self.assertEqual((novo_host.id, novo_host.nome), (segundo.participante.id, "Jorge"))
		self.assertFalse(next(p for p in resultado.participantes if p.id == terceiro.participante.id).eh_anfitriao)

	def test_abandono_de_nao_host_nao_transfere_host(self):
		sala = self.criar()
		segundo = self.entrar(sala.sala.codigo, "Jorge")
		with self.sessions() as session:
			resultado = self.service.abandonar(
				session, sala.sala.codigo, segundo.credencial_participante
			)
		self.assertEqual(sum(p.eh_anfitriao for p in resultado.participantes), 1)
		self.assertEqual(next(p.nome for p in resultado.participantes if p.eh_anfitriao), "Levi")

	def test_sem_ativos_fica_sem_host_e_novo_entrada_assume(self):
		sala = self.criar()
		with self.sessions() as session:
			estado = self.service.abandonar(
				session, sala.sala.codigo, sala.credencial_participante
			)
		self.assertEqual(estado.participantes_ativos, 0)
		novo = self.entrar(sala.sala.codigo, "Novo")
		self.assertTrue(novo.participante.eh_anfitriao)
		self.assertEqual(novo.participante.ordem_entrada, 2)

	def test_abandono_incrementa_versao_uma_vez_e_preserva_registro(self):
		sala = self.criar()
		segundo = self.entrar(sala.sala.codigo, "Jorge")
		terceira_versao = segundo.sala.versao
		with self.sessions() as session:
			estado = self.service.abandonar(
				session, sala.sala.codigo, sala.credencial_participante
			)
		self.assertEqual(estado.versao, terceira_versao + 1)
		abandonado = self.participante(sala.participante.id)
		self.assertEqual(abandonado.status, ParticipanteNemPatoStatus.ABANDONOU)
		self.assertIsNotNone(abandonado.saiu_em)
		with self.sessions() as session:
			with self.assertRaises(Exception) as repetido:
				self.service.abandonar(
					session, sala.sala.codigo, sala.credencial_participante
				)
		self.assertEqual(repetido.exception.status_code, 403)
		self.assertEqual(self.sala_db(sala.sala.codigo).estado_versao, estado.versao)

	def test_recuperacao_em_sessao_nova_e_token_de_outra_sala(self):
		sala_a = self.criar()
		sala_b = self.criar("Bia")
		with self.sessions() as nova_sessao:
			recuperada = self.service.recuperar(
				nova_sessao, sala_a.sala.codigo, sala_a.credencial_participante
			)
			self.assertEqual(recuperada.participante.id, sala_a.participante.id)
		with self.sessions() as session:
			with self.assertRaises(Exception) as erro:
				self.service.recuperar(
					session, sala_b.sala.codigo, sala_a.credencial_participante
				)
		self.assertEqual(erro.exception.status_code, 403)

	def test_token_de_participante_abandonado_nao_autoriza_nova_acao(self):
		sala = self.criar()
		with self.sessions() as session:
			self.service.abandonar(
				session, sala.sala.codigo, sala.credencial_participante
			)
		novo = self.entrar(sala.sala.codigo, "Novo")
		self.assertNotEqual(novo.participante.id, sala.participante.id)
		self.assertEqual(novo.participante.ordem_entrada, 2)
		with self.sessions() as session:
			with self.assertRaises(Exception) as recuperacao:
				self.service.recuperar(
					session, sala.sala.codigo, sala.credencial_participante
				)
		self.assertEqual(recuperacao.exception.status_code, 403)


class TestLobbyNemAPatoApi(SalasNemAPatoTestCase):
	def test_cors_permite_header_de_credencial_temporaria(self):
		with self.client() as client:
			resposta = client.options(
				"/api/v1/nem-pato/salas/NPABCD/eu",
				headers={
					"Origin": "http://localhost:5173",
					"Access-Control-Request-Method": "GET",
					"Access-Control-Request-Headers": HEADER_TOKEN_NEM_PATO.lower(),
				},
			)
		self.assertEqual(resposta.status_code, 200)
		self.assertIn(
			HEADER_TOKEN_NEM_PATO.lower(),
			resposta.headers["access-control-allow-headers"].lower(),
		)

	def test_criar_e_entrar_retorna_token_uma_vez_e_nao_vaza_hash(self):
		with self.client() as client:
			criado = client.post("/api/v1/nem-pato/salas", json={"nome": "Levi"})
			self.assertEqual(criado.status_code, 201, criado.text)
			dados = criado.json()
			token = dados["credencial_participante"]
			self.assertTrue(token)
			self.assertNotIn("token_hash", criado.text)
			codigo = dados["sala"]["codigo"]
			entrou = client.post(
				f"/api/v1/nem-pato/salas/{codigo}/participantes",
				json={"nome": "Jorge"},
			)
			self.assertEqual(entrou.status_code, 201, entrou.text)
			self.assertIn("credencial_participante", entrou.json())
			public = client.get(f"/api/v1/nem-pato/salas/{codigo}")
			self.assertEqual(public.status_code, 200)
			self.assertNotIn("credencial_participante", public.text)
			self.assertNotIn("token_hash", public.text)

	def test_endpoints_publico_recuperacao_abandono_e_auth_token(self):
		with self.client() as client:
			criado = client.post("/api/v1/nem-pato/salas", json={"nome": "Levi"}).json()
			codigo = criado["sala"]["codigo"]
			token = criado["credencial_participante"]
			self.assertEqual(
				client.get(f"/api/v1/nem-pato/salas/{codigo}/eu").status_code, 401
			)
			self.assertEqual(
				client.get(
					f"/api/v1/nem-pato/salas/{codigo}/eu",
					headers={HEADER_TOKEN_NEM_PATO: "token-invalido"},
				).status_code,
				401,
			)
			recuperada = client.get(
				f"/api/v1/nem-pato/salas/{codigo}/eu",
				headers={HEADER_TOKEN_NEM_PATO: token},
			)
			self.assertEqual(recuperada.status_code, 200, recuperada.text)
			self.assertEqual(recuperada.json()["participante"]["nome"], "Levi")
			self.assertNotIn("credencial_participante", recuperada.text)
			abandono = client.post(
				f"/api/v1/nem-pato/salas/{codigo}/abandonar",
				headers={HEADER_TOKEN_NEM_PATO: token},
			)
			self.assertEqual(abandono.status_code, 200, abandono.text)
			novamente = client.get(
				f"/api/v1/nem-pato/salas/{codigo}/eu",
				headers={HEADER_TOKEN_NEM_PATO: token},
			)
			self.assertEqual(novamente.status_code, 403)
			sem_token = client.post(
				f"/api/v1/nem-pato/salas/{codigo}/abandonar"
			)
			self.assertEqual(sem_token.status_code, 401)

	def test_schemas_rejeitam_nome_vazio_e_public_get_sala_inexistente(self):
		with self.client() as client:
			vazio = client.post("/api/v1/nem-pato/salas", json={"nome": "   "})
			self.assertEqual(vazio.status_code, 422)
			inexistente = client.get("/api/v1/nem-pato/salas/ZZZZZZ")
			self.assertEqual(inexistente.status_code, 404)