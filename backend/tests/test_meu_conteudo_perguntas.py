import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.conteudo import (
    MODO_NEM_A_PATO,
    MODO_QUIZ_CLASSICO,
    ORIGEM_OFICIAL,
    ORIGEM_USUARIO,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Categoria, Jogador, JogadorPartidaNemPato, Partida, PartidaNemPato,
    PartidaPergunta, ParticipanteNemPato, Pergunta, PerguntaNemPato,
    RodadaNemPato, SalaNemPato, Usuario,
)
from app.nem_a_pato import RodadaNemPatoStatus
from app.security import usuario_atual
from app.services.partidas import PartidasPersistentes
from app.services.salas_nem_a_pato import SalasNemAPatoService


class MeuConteudoPerguntasTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            self.usuario = Usuario(
                nome="Ana", email=f"ana-{uuid4()}@example.com", senha_hash="hash"
            )
            self.outro = Usuario(
                nome="Bia", email=f"bia-{uuid4()}@example.com", senha_hash="hash"
            )
            db.add_all((self.usuario, self.outro))
            db.commit()

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[usuario_atual] = lambda: self.usuario
        self.client = TestClient(app)
        self.classica = self.categoria("Clássica", MODO_QUIZ_CLASSICO)
        self.nem_pato = self.categoria("NP", MODO_NEM_A_PATO)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def categoria(
        self, nome, modo, *, usuario=None, origem=ORIGEM_USUARIO,
        ativa=True, excluida=False,
    ):
        usuario = usuario or self.usuario
        categoria = Categoria(
            id=uuid4(), slug=f"cat-{uuid4().hex[:8]}", nome=nome, modo=modo,
            origem=origem,
            usuario_id=usuario.id if origem == ORIGEM_USUARIO else None,
            ativa=False if excluida else ativa,
            excluida_em=datetime.now(timezone.utc) if excluida else None,
        )
        with self.sessions() as db:
            db.add(categoria)
            db.commit()
        return categoria

    def payload_classico(self, categoria_id=None, **alteracoes):
        return {
            "categoria_id": str(categoria_id or self.classica.id),
            "enunciado": "  Qual é a resposta?  ",
            "alternativa_a": " Um ", "alternativa_b": " Dois ",
            "alternativa_c": " Três ", "alternativa_d": " Quatro ",
            "alternativa_correta": "B", "explicacao": " Porque sim. ",
            **alteracoes,
        }

    def payload_np(self, categoria_id=None, **alteracoes):
        return {
            "categoria_id": str(categoria_id or self.nem_pato.id),
            "enunciado": " Quantos existem? ", "resposta_numerica": 42,
            "unidade": " itens ", "explicacao": " Explicação. ",
            "fonte": " Fonte ", **alteracoes,
        }

    def criar_classica(self, **alteracoes):
        return self.client.post(
            "/api/v1/meu-conteudo/perguntas/classico",
            json=self.payload_classico(**alteracoes),
        )

    def criar_np(self, **alteracoes):
        return self.client.post(
            "/api/v1/meu-conteudo/perguntas/nem-a-pato",
            json=self.payload_np(**alteracoes),
        )

    def test_todos_os_endpoints_rejeitam_guest(self):
        app.dependency_overrides.pop(usuario_atual)
        casos = (
            ("GET", "/api/v1/meu-conteudo/perguntas/classico", None),
            ("POST", "/api/v1/meu-conteudo/perguntas/classico", self.payload_classico()),
            ("GET", "/api/v1/meu-conteudo/perguntas/classico/1", None),
            ("PATCH", "/api/v1/meu-conteudo/perguntas/classico/1", {"ativa": False}),
            ("DELETE", "/api/v1/meu-conteudo/perguntas/classico/1", None),
            ("GET", "/api/v1/meu-conteudo/perguntas/nem-a-pato", None),
            ("POST", "/api/v1/meu-conteudo/perguntas/nem-a-pato", self.payload_np()),
            ("GET", "/api/v1/meu-conteudo/perguntas/nem-a-pato/1", None),
            ("PATCH", "/api/v1/meu-conteudo/perguntas/nem-a-pato/1", {"ativa": False}),
            ("DELETE", "/api/v1/meu-conteudo/perguntas/nem-a-pato/1", None),
        )
        for metodo, caminho, corpo in casos:
            with self.subTest(metodo=metodo, caminho=caminho):
                self.assertEqual(
                    self.client.request(metodo, caminho, json=corpo).status_code, 401
                )

    def test_cria_classica_normalizada_com_owner_origem_id_e_alternativas(self):
        resposta = self.criar_classica()
        self.assertEqual(resposta.status_code, 201)
        corpo = resposta.json()
        self.assertEqual(corpo["enunciado"], "Qual é a resposta?")
        self.assertEqual(corpo["alternativa_b"], "Dois")
        self.assertEqual(corpo["alternativa_correta"], "B")
        self.assertEqual(corpo["explicacao"], "Porque sim.")
        self.assertTrue(corpo["ativa"])
        self.assertIsInstance(corpo["id"], int)
        with self.sessions() as db:
            pergunta = db.get(Pergunta, corpo["id"])
            self.assertEqual(pergunta.alternativa_correta, 1)
            self.assertEqual((pergunta.origem, pergunta.usuario_id), (ORIGEM_USUARIO, self.usuario.id))

    def test_cria_np_preserva_inteiro_e_normaliza_opcionais(self):
        resposta = self.criar_np()
        self.assertEqual(resposta.status_code, 201)
        corpo = resposta.json()
        self.assertEqual(corpo["resposta_numerica"], 42)
        self.assertEqual(corpo["unidade"], "itens")
        self.assertEqual(corpo["fonte"], "Fonte")
        self.assertTrue(corpo["ativa"])
        with self.sessions() as db:
            pergunta = db.get(PerguntaNemPato, corpo["id"])
            self.assertEqual((pergunta.origem, pergunta.usuario_id), (ORIGEM_USUARIO, self.usuario.id))

    def test_create_valida_textos_alternativa_numero_e_campos_proibidos(self):
        casos = (
            ("classico", self.payload_classico(enunciado=" ")),
            ("classico", self.payload_classico(alternativa_a=" ")),
            ("classico", self.payload_classico(alternativa_correta="E")),
            ("classico", self.payload_classico(origem=ORIGEM_OFICIAL)),
            ("nem-a-pato", self.payload_np(enunciado=" ")),
            ("nem-a-pato", self.payload_np(explicacao=" ")),
            ("nem-a-pato", self.payload_np(resposta_numerica=-1)),
            ("nem-a-pato", self.payload_np(resposta_numerica=2**63)),
            ("nem-a-pato", self.payload_np(usuario_id=str(self.usuario.id))),
        )
        for modo, payload in casos:
            with self.subTest(modo=modo, payload=payload):
                resposta = self.client.post(
                    f"/api/v1/meu-conteudo/perguntas/{modo}", json=payload
                )
                self.assertEqual(resposta.status_code, 422)

    def test_resposta_numerica_post_e_patch_exigem_inteiro_json_estrito(self):
        validos = (0, 1, 42)
        for valor in validos:
            with self.subTest(operacao="POST", valor=valor):
                resposta = self.criar_np(resposta_numerica=valor)
                self.assertEqual(resposta.status_code, 201)
                self.assertEqual(resposta.json()["resposta_numerica"], valor)

        invalidos = (True, False, "42", 42.0, 42.5, -1, 2**63)
        for valor in invalidos:
            with self.subTest(operacao="POST", valor=valor):
                with self.sessions() as db:
                    antes = len(list(db.scalars(select(PerguntaNemPato))))
                resposta = self.criar_np(resposta_numerica=valor)
                self.assertEqual(resposta.status_code, 422)
                with self.sessions() as db:
                    depois = len(list(db.scalars(select(PerguntaNemPato))))
                self.assertEqual(depois, antes)

        pergunta = self.criar_np(resposta_numerica=10).json()
        caminho = f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta['id']}"
        for valor in invalidos:
            with self.subTest(operacao="PATCH", valor=valor):
                resposta = self.client.patch(caminho, json={"resposta_numerica": valor})
                self.assertEqual(resposta.status_code, 422)
                self.assertEqual(self.client.get(caminho).json()["resposta_numerica"], 10)

    def test_create_rejeita_categoria_oficial_alheia_modo_errado_inativa_e_excluida(self):
        categorias = (
            self.categoria("Oficial", MODO_QUIZ_CLASSICO, origem=ORIGEM_OFICIAL),
            self.categoria("Alheia", MODO_QUIZ_CLASSICO, usuario=self.outro),
            self.nem_pato,
            self.categoria("Inativa", MODO_QUIZ_CLASSICO, ativa=False),
            self.categoria("Excluída", MODO_QUIZ_CLASSICO, excluida=True),
        )
        esperados = (404, 404, 404, 409, 409)
        for categoria, esperado in zip(categorias, esperados, strict=True):
            with self.subTest(categoria=categoria.nome):
                resposta = self.criar_classica(categoria_id=categoria.id)
                self.assertEqual(resposta.status_code, esperado)

        categorias_np = (
            self.categoria("Oficial NP", MODO_NEM_A_PATO, origem=ORIGEM_OFICIAL),
            self.categoria("Alheia NP", MODO_NEM_A_PATO, usuario=self.outro),
            self.classica,
            self.categoria("Inativa NP", MODO_NEM_A_PATO, ativa=False),
            self.categoria("Excluída NP", MODO_NEM_A_PATO, excluida=True),
        )
        for categoria, esperado in zip(categorias_np, esperados, strict=True):
            with self.subTest(categoria=categoria.nome):
                resposta = self.criar_np(categoria_id=categoria.id)
                self.assertEqual(resposta.status_code, esperado)

    def test_listagem_isola_filtra_paginar_ordena_e_valida_categoria(self):
        primeira = self.criar_classica(enunciado="Primeira").json()
        segunda = self.criar_classica(enunciado="Segunda").json()
        terceira = self.criar_classica(enunciado="Terceira").json()
        self.client.patch(
            f"/api/v1/meu-conteudo/perguntas/classico/{segunda['id']}",
            json={"ativa": False},
        )
        self.client.delete(
            f"/api/v1/meu-conteudo/perguntas/classico/{terceira['id']}"
        )
        app.dependency_overrides[usuario_atual] = lambda: self.outro
        categoria_outro = self.categoria("Outra 2", MODO_QUIZ_CLASSICO, usuario=self.outro)
        outra = self.client.post(
            "/api/v1/meu-conteudo/perguntas/classico",
            json=self.payload_classico(categoria_id=categoria_outro.id, enunciado="Alheia"),
        )
        self.assertEqual(outra.status_code, 201)
        app.dependency_overrides[usuario_atual] = lambda: self.usuario

        resposta = self.client.get(
            "/api/v1/meu-conteudo/perguntas/classico",
            params={"include_deleted": True, "offset": 1, "limit": 2},
        )
        self.assertEqual([item["id"] for item in resposta.json()], [segunda["id"], terceira["id"]])
        ativos = self.client.get(
            "/api/v1/meu-conteudo/perguntas/classico",
            params={"categoria_id": str(self.classica.id), "ativa": True},
        )
        self.assertEqual([item["id"] for item in ativos.json()], [primeira["id"]])
        self.assertEqual(
            self.client.get(
                "/api/v1/meu-conteudo/perguntas/classico",
                params={"categoria_id": str(categoria_outro.id)},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/v1/meu-conteudo/perguntas/classico", params={"limit": 101}).status_code,
            422,
        )

    def test_listagem_nem_pato_aplica_filtros_e_include_deleted(self):
        primeira = self.criar_np(enunciado="Primeira").json()
        segunda = self.criar_np(enunciado="Segunda").json()
        self.client.patch(
            f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{segunda['id']}",
            json={"ativa": False},
        )
        terceira = self.criar_np(enunciado="Terceira").json()
        self.client.delete(
            f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{terceira['id']}"
        )

        ativas = self.client.get(
            "/api/v1/meu-conteudo/perguntas/nem-a-pato",
            params={"categoria_id": str(self.nem_pato.id), "ativa": True},
        )
        self.assertEqual([item["id"] for item in ativas.json()], [primeira["id"]])
        todas = self.client.get(
            "/api/v1/meu-conteudo/perguntas/nem-a-pato",
            params={"include_deleted": True, "offset": 1, "limit": 2},
        )
        self.assertEqual([item["id"] for item in todas.json()], [segunda["id"], terceira["id"]])

    def test_paginacao_rejeita_offset_negativo_e_limites_fora_da_faixa(self):
        for endpoint in ("classico", "nem-a-pato"):
            for parametros in ({"offset": -1}, {"limit": 0}, {"limit": 101}):
                with self.subTest(endpoint=endpoint, parametros=parametros):
                    resposta = self.client.get(
                        f"/api/v1/meu-conteudo/perguntas/{endpoint}",
                        params=parametros,
                    )
                    self.assertEqual(resposta.status_code, 422)

    def test_filtro_categoria_id_preserva_seguranca_e_administracao(self):
        propria_inativa = self.categoria("Inativa filtro", MODO_QUIZ_CLASSICO, ativa=False)
        propria_excluida = self.categoria("Excluída filtro", MODO_QUIZ_CLASSICO, excluida=True)
        oficial = self.categoria("Oficial filtro", MODO_QUIZ_CLASSICO, origem=ORIGEM_OFICIAL)
        alheia = self.categoria("Alheia filtro", MODO_QUIZ_CLASSICO, usuario=self.outro)
        casos_200 = (self.classica.id, propria_inativa.id, propria_excluida.id)
        for categoria_id in casos_200:
            with self.subTest(resultado=200, categoria_id=categoria_id):
                resposta = self.client.get(
                    "/api/v1/meu-conteudo/perguntas/classico",
                    params={"categoria_id": str(categoria_id), "include_deleted": True},
                )
                self.assertEqual(resposta.status_code, 200)
        casos_404 = (uuid4(), oficial.id, alheia.id, self.nem_pato.id)
        for categoria_id in casos_404:
            with self.subTest(resultado=404, categoria_id=categoria_id):
                resposta = self.client.get(
                    "/api/v1/meu-conteudo/perguntas/classico",
                    params={"categoria_id": str(categoria_id)},
                )
                self.assertEqual(resposta.status_code, 404)

    def test_quotas_classic_e_nem_pato_sao_independentes(self):
        with self.sessions() as db:
            db.add_all(Pergunta(
                id=20000 + indice, categoria_id=self.classica.id,
                enunciado=f"Q {indice}", alternativa_a="A", alternativa_b="B",
                alternativa_c="C", alternativa_d="D", alternativa_correta=0,
                explicacao="E", origem=ORIGEM_USUARIO, usuario_id=self.usuario.id,
            ) for indice in range(200))
            db.commit()

        self.assertEqual(self.criar_classica().status_code, 409)
        self.assertEqual(self.criar_np().status_code, 201)

    def test_detalhe_proprio_deleted_e_oculta_oficial_alheia_inexistente(self):
        propria = self.criar_np().json()
        self.client.delete(f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{propria['id']}")
        with self.sessions() as db:
            oficial = PerguntaNemPato(
                categoria_id=self.nem_pato.id, enunciado="Oficial", resposta_numerica=1,
                explicacao="E", origem=ORIGEM_OFICIAL,
            )
            alheia = PerguntaNemPato(
                categoria_id=self.nem_pato.id, enunciado="Alheia", resposta_numerica=2,
                explicacao="E", origem=ORIGEM_USUARIO, usuario_id=self.outro.id,
            )
            db.add_all((oficial, alheia))
            db.commit()
            ids = (oficial.id, alheia.id, 999999)
        self.assertEqual(
            self.client.get(f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{propria['id']}").status_code,
            200,
        )
        for pergunta_id in ids:
            self.assertEqual(
                self.client.get(f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta_id}").status_code,
                404,
            )

    def test_detalhe_proprio_ativo_e_id_invalido_nos_dois_modos(self):
        classica = self.criar_classica().json()
        nem_pato = self.criar_np().json()
        for endpoint, pergunta in (("classico", classica), ("nem-a-pato", nem_pato)):
            with self.subTest(endpoint=endpoint):
                resposta = self.client.get(
                    f"/api/v1/meu-conteudo/perguntas/{endpoint}/{pergunta['id']}"
                )
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.json()["ativa"])
                invalida = self.client.get(
                    f"/api/v1/meu-conteudo/perguntas/{endpoint}/texto"
                )
                self.assertEqual(invalida.status_code, 422)

    def test_patch_classico_todos_campos_move_inativa_e_reativa(self):
        pergunta = self.criar_classica().json()
        destino = self.categoria("Destino", MODO_QUIZ_CLASSICO)
        resposta = self.client.patch(
            f"/api/v1/meu-conteudo/perguntas/classico/{pergunta['id']}",
            json={
                "categoria_id": str(destino.id), "enunciado": "Novo",
                "alternativa_a": "A1", "alternativa_b": "B1",
                "alternativa_c": "C1", "alternativa_d": "D1",
                "alternativa_correta": "D", "explicacao": "Nova", "ativa": False,
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["categoria_id"], str(destino.id))
        self.assertEqual(resposta.json()["alternativa_correta"], "D")
        self.assertFalse(resposta.json()["ativa"])
        with self.sessions() as db:
            destino_db = db.get(Categoria, destino.id)
            destino_db.ativa = False
            db.commit()
        editada = self.client.patch(
            f"/api/v1/meu-conteudo/perguntas/classico/{pergunta['id']}",
            json={"enunciado": "Ainda editável"},
        )
        self.assertEqual(editada.status_code, 200)
        reativada = self.client.patch(
            f"/api/v1/meu-conteudo/perguntas/classico/{pergunta['id']}",
            json={"ativa": True},
        )
        self.assertEqual(reativada.status_code, 409)

    def test_reativa_em_categoria_ativa_e_aceita_categoria_id_atual(self):
        pergunta = self.criar_classica().json()
        caminho = f"/api/v1/meu-conteudo/perguntas/classico/{pergunta['id']}"
        self.assertEqual(self.client.patch(caminho, json={"ativa": False}).status_code, 200)
        resposta = self.client.patch(
            caminho,
            json={"categoria_id": str(self.classica.id), "ativa": True},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ativa"])
        self.assertEqual(resposta.json()["categoria_id"], str(self.classica.id))

    def test_patch_np_todos_campos_e_rejeita_movimento_para_inativa(self):
        pergunta = self.criar_np().json()
        destino = self.categoria("Destino NP", MODO_NEM_A_PATO)
        resposta = self.client.patch(
            f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta['id']}",
            json={
                "categoria_id": str(destino.id), "enunciado": "Novo",
                "resposta_numerica": 0, "unidade": None,
                "explicacao": "Nova", "fonte": None, "ativa": False,
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resposta_numerica"], 0)
        self.assertIsNone(resposta.json()["unidade"])
        inativa = self.categoria("Inativa NP", MODO_NEM_A_PATO, ativa=False)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta['id']}",
                json={"categoria_id": str(inativa.id)},
            ).status_code,
            409,
        )

    def test_patch_rejeita_vazio_imutaveis_deleted_e_ownership(self):
        pergunta = self.criar_classica().json()
        caminho = f"/api/v1/meu-conteudo/perguntas/classico/{pergunta['id']}"
        self.assertEqual(self.client.patch(caminho, json={}).status_code, 422)
        for campo in ("id", "origem", "usuario_id", "criada_em", "atualizada_em", "excluida_em"):
            with self.subTest(campo=campo):
                self.assertEqual(self.client.patch(caminho, json={campo: 1}).status_code, 422)
        self.assertEqual(self.client.delete(caminho).status_code, 204)
        self.assertEqual(self.client.patch(caminho, json={"enunciado": "X"}).status_code, 409)
        outra_categoria = self.categoria("Outra", MODO_QUIZ_CLASSICO, usuario=self.outro)
        app.dependency_overrides[usuario_atual] = lambda: self.outro
        alheia = self.client.post(
            "/api/v1/meu-conteudo/perguntas/classico",
            json=self.payload_classico(categoria_id=outra_categoria.id),
        ).json()
        app.dependency_overrides[usuario_atual] = lambda: self.usuario
        self.assertEqual(
            self.client.patch(
                f"/api/v1/meu-conteudo/perguntas/classico/{alheia['id']}",
                json={"enunciado": "X"},
            ).status_code,
            404,
        )

    def test_patch_np_rejeita_todos_campos_imutaveis_sem_alterar_pergunta(self):
        pergunta = self.criar_np().json()
        caminho = f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta['id']}"
        valores = {
            "id": 999, "origem": ORIGEM_OFICIAL,
            "usuario_id": str(self.outro.id),
            "criada_em": datetime.now(timezone.utc).isoformat(),
            "atualizada_em": datetime.now(timezone.utc).isoformat(),
            "excluida_em": datetime.now(timezone.utc).isoformat(),
        }
        for campo, valor in valores.items():
            with self.subTest(campo=campo):
                self.assertEqual(
                    self.client.patch(caminho, json={campo: valor}).status_code, 422
                )
        preservada = self.client.get(caminho).json()
        self.assertEqual(preservada, pergunta)

    def test_delete_soft_delete_204_include_detail_repeticao_e_libera_quota(self):
        with self.sessions() as db:
            db.add_all(PerguntaNemPato(
                categoria_id=self.nem_pato.id, enunciado=f"Q {indice}",
                resposta_numerica=indice, explicacao="E", origem=ORIGEM_USUARIO,
                usuario_id=self.usuario.id,
            ) for indice in range(200))
            db.commit()
        self.assertEqual(self.criar_np().status_code, 409)
        with self.sessions() as db:
            pergunta_id = db.scalar(select(PerguntaNemPato.id).where(
                PerguntaNemPato.usuario_id == self.usuario.id
            ).order_by(PerguntaNemPato.id))
        resposta = self.client.delete(
            f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta_id}"
        )
        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(resposta.content, b"")
        self.assertEqual(self.criar_np().status_code, 201)
        detalhe = self.client.get(
            f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta_id}"
        )
        self.assertEqual(detalhe.status_code, 200)
        self.assertIsNotNone(detalhe.json()["excluida_em"])
        lista = self.client.get(
            "/api/v1/meu-conteudo/perguntas/nem-a-pato",
            params={"include_deleted": True, "limit": 100},
        )
        self.assertIn(pergunta_id, [item["id"] for item in lista.json()])
        self.assertEqual(
            self.client.delete(f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta_id}").status_code,
            409,
        )

    def test_snapshot_classico_permanece_apos_edicao_e_exclusao_da_pergunta(self):
        pergunta = self.criar_classica().json()
        with self.sessions() as db:
            original = db.get(Pergunta, pergunta["id"])
            ocorrencia = PartidaPergunta(
                partida=Partida(
                    jogador=Jogador(nome="Histórico"), categoria_id=self.classica.id
                ),
                pergunta=original,
                ordem=1,
                disponibilizada_em=datetime.now(timezone.utc),
                prazo_resposta_em=datetime.now(timezone.utc) + timedelta(minutes=1),
                categoria_id_snapshot=original.categoria_id,
                enunciado_snapshot=original.enunciado,
                alternativa_a_snapshot=original.alternativa_a,
                alternativa_b_snapshot=original.alternativa_b,
                alternativa_c_snapshot=original.alternativa_c,
                alternativa_d_snapshot=original.alternativa_d,
                alternativa_correta_snapshot=original.alternativa_correta,
                explicacao_snapshot=original.explicacao,
            )
            db.add(ocorrencia)
            db.commit()
            ocorrencia_id = ocorrencia.id

        caminho = f"/api/v1/meu-conteudo/perguntas/classico/{pergunta['id']}"
        self.assertEqual(self.client.patch(caminho, json={
            "enunciado": "Alterado", "alternativa_a": "Alterada A",
            "alternativa_b": "Alterada B", "alternativa_c": "Alterada C",
            "alternativa_d": "Alterada D", "alternativa_correta": "D",
            "explicacao": "Alterada",
        }).status_code, 200)
        self.assertEqual(self.client.delete(caminho).status_code, 204)

        with self.sessions() as db:
            ocorrencia = db.get(PartidaPergunta, ocorrencia_id)
            publica = PartidasPersistentes._pergunta_publica(ocorrencia)
            self.assertEqual(publica.pergunta, "Qual é a resposta?")
            self.assertEqual(publica.alternativas, ["Um", "Dois", "Três", "Quatro"])
            resultado = PartidasPersistentes().responder(
                db, str(ocorrencia.partida_id), ocorrencia.pergunta_id, 1
            )
            self.assertTrue(resultado.correta)
            self.assertEqual(resultado.alternativa_correta, 1)
            self.assertEqual(resultado.explicacao, "Porque sim.")

    def test_snapshot_nem_pato_permanece_apos_edicao_e_exclusao_da_pergunta(self):
        pergunta = self.criar_np().json()
        with self.sessions() as db:
            original = db.get(PerguntaNemPato, pergunta["id"])
            sala = SalaNemPato(codigo=f"H{uuid4().hex[:7].upper()}")
            participante = ParticipanteNemPato(
                sala=sala, nome="Histórico", token_hash=b"x" * 32,
                ordem_entrada=1, eh_anfitriao=True,
            )
            partida = PartidaNemPato(
                sala=sala, categoria_id=self.nem_pato.id, numero=1,
            )
            jogador = JogadorPartidaNemPato(
                partida=partida, participante=participante, ordem_circular=1,
                nome_snapshot="Histórico",
            )
            rodada = RodadaNemPato(
                partida=partida, pergunta=original, numero=1,
                status=RodadaNemPatoStatus.RESULTADO,
                jogador_inicial=jogador,
                categoria_id_snapshot=original.categoria_id,
                enunciado_snapshot=original.enunciado,
                resposta_numerica_snapshot=original.resposta_numerica,
                explicacao_snapshot=original.explicacao,
                unidade_snapshot=original.unidade,
                fonte_snapshot=original.fonte,
            )
            db.add(rodada)
            db.commit()
            rodada_id = rodada.id

        caminho = f"/api/v1/meu-conteudo/perguntas/nem-a-pato/{pergunta['id']}"
        self.assertEqual(self.client.patch(caminho, json={
            "enunciado": "Alterado", "resposta_numerica": 999,
            "explicacao": "Alterada", "unidade": "outra", "fonte": "outra",
        }).status_code, 200)
        self.assertEqual(self.client.delete(caminho).status_code, 204)

        with self.sessions() as db:
            rodada = db.get(RodadaNemPato, rodada_id)
            estado = SalasNemAPatoService()._partida_publica(
                db, rodada.partida, rodada.jogador_inicial.participante_id
            )
            pergunta_publica = estado.rodada.pergunta
            self.assertEqual(pergunta_publica.enunciado, "Quantos existem?")
            self.assertEqual(pergunta_publica.resposta_numerica, 42)
            self.assertEqual(pergunta_publica.explicacao, "Explicação.")
            self.assertEqual(pergunta_publica.unidade, "itens")
            # A API pública atual não expõe fonte; sua preservação continua
            # garantida pelo snapshot materializado para uso futuro.
            self.assertEqual(rodada.fonte_snapshot, "Fonte")


if __name__ == "__main__":
    unittest.main()
