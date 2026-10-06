import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

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
from app.models import Categoria, Pergunta, PerguntaNemPato, Usuario
from app.security import usuario_atual


class MeuConteudoCategoriasTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
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
            db.refresh(self.usuario)
            db.refresh(self.outro)

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[usuario_atual] = lambda: self.usuario
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def categoria(
        self,
        nome="Categoria",
        modo=MODO_QUIZ_CLASSICO,
        *,
        usuario=None,
        ativa=True,
        excluida=False,
        origem=ORIGEM_USUARIO,
    ):
        proprietario = usuario if usuario is not None else self.usuario
        categoria = Categoria(
            id=uuid4(),
            slug=f"categoria-{uuid4().hex[:8]}",
            nome=nome,
            modo=modo,
            origem=origem,
            usuario_id=proprietario.id if origem == ORIGEM_USUARIO else None,
            ativa=False if excluida else ativa,
            excluida_em=(datetime.now(timezone.utc) if excluida else None),
        )
        with self.sessions() as db:
            db.add(categoria)
            db.commit()
            db.refresh(categoria)
        return categoria

    def criar(self, nome="Ciência", modo=MODO_QUIZ_CLASSICO, **extra):
        return self.client.post(
            "/api/v1/meu-conteudo/categorias",
            json={"nome": nome, "modo": modo, **extra},
        )

    def test_todos_os_endpoints_rejeitam_guest(self):
        app.dependency_overrides.pop(usuario_atual)
        caminhos = (
            ("GET", "/api/v1/meu-conteudo/resumo", None),
            ("GET", "/api/v1/meu-conteudo/categorias", None),
            ("POST", "/api/v1/meu-conteudo/categorias", {"nome": "X", "modo": MODO_QUIZ_CLASSICO}),
            ("GET", f"/api/v1/meu-conteudo/categorias/{uuid4()}", None),
            ("PATCH", f"/api/v1/meu-conteudo/categorias/{uuid4()}", {"nome": "X"}),
            ("DELETE", f"/api/v1/meu-conteudo/categorias/{uuid4()}", None),
        )
        for metodo, caminho, json in caminhos:
            with self.subTest(metodo=metodo, caminho=caminho):
                resposta = self.client.request(metodo, caminho, json=json)
                self.assertEqual(resposta.status_code, 401)

    def test_resumo_separa_modos_e_ignora_excluido_oficial_e_outro_usuario(self):
        classica = self.categoria("Clássica ativa")
        self.categoria("Clássica inativa", ativa=False)
        nem = self.categoria("Nem", MODO_NEM_A_PATO)
        excluida = self.categoria("Excluída", excluida=True)
        self.categoria("Outra", usuario=self.outro)
        self.categoria("Oficial", origem=ORIGEM_OFICIAL)
        with self.sessions() as db:
            db.add_all((
                Pergunta(
                    id=9001, categoria_id=classica.id, enunciado="Q", alternativa_a="A",
                    alternativa_b="B", alternativa_c="C", alternativa_d="D",
                    alternativa_correta=0, explicacao="E", origem=ORIGEM_USUARIO,
                    usuario_id=self.usuario.id,
                ),
                PerguntaNemPato(
                    categoria_id=nem.id, enunciado="N", resposta_numerica=1,
                    explicacao="E", origem=ORIGEM_USUARIO, usuario_id=self.usuario.id,
                    ativa=False,
                ),
                Pergunta(
                    id=9002, categoria_id=excluida.id, enunciado="Q2", alternativa_a="A",
                    alternativa_b="B", alternativa_c="C", alternativa_d="D",
                    alternativa_correta=0, explicacao="E", origem=ORIGEM_USUARIO,
                    usuario_id=self.usuario.id, ativa=False,
                    excluida_em=datetime.now(timezone.utc),
                ),
            ))
            db.commit()
        resposta = self.client.get("/api/v1/meu-conteudo/resumo")
        self.assertEqual(resposta.status_code, 200)
        modos = {item["modo"]: item for item in resposta.json()["modos"]}
        self.assertEqual(modos[MODO_QUIZ_CLASSICO]["categorias"], {"usadas": 2, "limite": 10})
        self.assertEqual(modos[MODO_QUIZ_CLASSICO]["perguntas"], {"usadas": 1, "limite": 200})
        self.assertEqual(modos[MODO_NEM_A_PATO]["categorias"]["usadas"], 1)
        self.assertEqual(modos[MODO_NEM_A_PATO]["perguntas"]["usadas"], 1)

    def test_resumo_zero_retorna_ambos_os_modos_e_limites(self):
        resposta = self.client.get("/api/v1/meu-conteudo/resumo")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json(),
            {
                "modos": [
                    {
                        "modo": MODO_QUIZ_CLASSICO,
                        "categorias": {"usadas": 0, "limite": 10},
                        "perguntas": {"usadas": 0, "limite": 200},
                    },
                    {
                        "modo": MODO_NEM_A_PATO,
                        "categorias": {"usadas": 0, "limite": 10},
                        "perguntas": {"usadas": 0, "limite": 200},
                    },
                ]
            },
        )

    def test_resumo_isola_origem_owner_e_soft_delete_nas_duas_tabelas(self):
        classica_propria = self.categoria("Clássica própria")
        classica_oficial = self.categoria("Clássica oficial", origem=ORIGEM_OFICIAL)
        classica_alheia = self.categoria("Clássica alheia", usuario=self.outro)
        nem_propria = self.categoria("NP própria", MODO_NEM_A_PATO)
        nem_oficial = self.categoria(
            "NP oficial", MODO_NEM_A_PATO, origem=ORIGEM_OFICIAL
        )
        nem_alheia = self.categoria(
            "NP alheia", MODO_NEM_A_PATO, usuario=self.outro
        )
        agora = datetime.now(timezone.utc)
        with self.sessions() as db:
            db.add_all((
                Pergunta(
                    id=9101, categoria_id=classica_propria.id, enunciado="Própria",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C",
                    alternativa_d="D", alternativa_correta=0, explicacao="E",
                    origem=ORIGEM_USUARIO, usuario_id=self.usuario.id,
                ),
                Pergunta(
                    id=9102, categoria_id=classica_propria.id, enunciado="Excluída",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C",
                    alternativa_d="D", alternativa_correta=0, explicacao="E",
                    origem=ORIGEM_USUARIO, usuario_id=self.usuario.id,
                    ativa=False, excluida_em=agora,
                ),
                Pergunta(
                    id=9103, categoria_id=classica_oficial.id, enunciado="Oficial",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C",
                    alternativa_d="D", alternativa_correta=0, explicacao="E",
                    origem=ORIGEM_OFICIAL,
                ),
                Pergunta(
                    id=9104, categoria_id=classica_alheia.id, enunciado="Alheia",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C",
                    alternativa_d="D", alternativa_correta=0, explicacao="E",
                    origem=ORIGEM_USUARIO, usuario_id=self.outro.id,
                ),
                PerguntaNemPato(
                    categoria_id=nem_propria.id, enunciado="Própria",
                    resposta_numerica=1, explicacao="E", origem=ORIGEM_USUARIO,
                    usuario_id=self.usuario.id,
                ),
                PerguntaNemPato(
                    categoria_id=nem_propria.id, enunciado="Excluída",
                    resposta_numerica=2, explicacao="E", origem=ORIGEM_USUARIO,
                    usuario_id=self.usuario.id, ativa=False, excluida_em=agora,
                ),
                PerguntaNemPato(
                    categoria_id=nem_oficial.id, enunciado="Oficial",
                    resposta_numerica=3, explicacao="E", origem=ORIGEM_OFICIAL,
                ),
                PerguntaNemPato(
                    categoria_id=nem_alheia.id, enunciado="Alheia",
                    resposta_numerica=4, explicacao="E", origem=ORIGEM_USUARIO,
                    usuario_id=self.outro.id,
                ),
            ))
            db.commit()

        resposta = self.client.get("/api/v1/meu-conteudo/resumo")
        modos = {item["modo"]: item for item in resposta.json()["modos"]}
        self.assertEqual(modos[MODO_QUIZ_CLASSICO]["perguntas"]["usadas"], 1)
        self.assertEqual(modos[MODO_NEM_A_PATO]["perguntas"]["usadas"], 1)

    def test_listagem_aplica_ownership_filtros_excluidos_e_ordem(self):
        self.categoria("zeta", MODO_NEM_A_PATO)
        self.categoria("Beta", ativa=False)
        self.categoria("alfa")
        excluida = self.categoria("Excluída", excluida=True)
        self.categoria("Outro", usuario=self.outro)
        self.categoria("Oficial", origem=ORIGEM_OFICIAL)
        resposta = self.client.get("/api/v1/meu-conteudo/categorias")
        self.assertEqual([item["nome"] for item in resposta.json()], ["zeta", "alfa", "Beta"])
        resposta = self.client.get(
            "/api/v1/meu-conteudo/categorias",
            params={"modo": MODO_QUIZ_CLASSICO, "ativa": False},
        )
        self.assertEqual([item["nome"] for item in resposta.json()], ["Beta"])
        resposta = self.client.get(
            "/api/v1/meu-conteudo/categorias", params={"include_deleted": True}
        )
        self.assertIn(str(excluida.id), [item["id"] for item in resposta.json()])

    def test_include_deleted_mantem_isolamento_de_owner_e_origem(self):
        propria_ativa = self.categoria("Própria ativa")
        propria_excluida = self.categoria("Própria excluída", excluida=True)
        alheia_excluida = self.categoria(
            "Alheia excluída", usuario=self.outro, excluida=True
        )
        oficial = self.categoria("Oficial", origem=ORIGEM_OFICIAL)

        resposta = self.client.get(
            "/api/v1/meu-conteudo/categorias", params={"include_deleted": True}
        )

        self.assertEqual(resposta.status_code, 200)
        ids = {item["id"] for item in resposta.json()}
        self.assertEqual(ids, {str(propria_ativa.id), str(propria_excluida.id)})
        self.assertNotIn(str(alheia_excluida.id), ids)
        self.assertNotIn(str(oficial.id), ids)

    def test_criacao_define_owner_origem_slug_e_valida_payload(self):
        for modo in (MODO_QUIZ_CLASSICO, MODO_NEM_A_PATO):
            with self.subTest(modo=modo):
                resposta = self.criar("  Ciências & Ação  ", modo, descricao="  teste  ")
                self.assertEqual(resposta.status_code, 201)
                corpo = resposta.json()
                self.assertEqual(corpo["nome"], "Ciências & Ação")
                self.assertEqual(corpo["descricao"], "teste")
                self.assertRegex(corpo["slug"], r"^ciencias-acao-[0-9a-f]{8}$")
                self.assertTrue(corpo["ativa"])
                with self.sessions() as db:
                    item = db.get(Categoria, UUID(corpo["id"]))
                    self.assertEqual((item.origem, item.usuario_id), (ORIGEM_USUARIO, self.usuario.id))
        casos = (
            ({"nome": " ", "modo": MODO_QUIZ_CLASSICO}, 422),
            ({"nome": "X", "modo": "INVALIDO"}, 422),
            ({"nome": "X", "modo": MODO_QUIZ_CLASSICO, "slug": "cliente"}, 422),
        )
        for payload, status in casos:
            self.assertEqual(self.client.post("/api/v1/meu-conteudo/categorias", json=payload).status_code, status)

    def test_slug_usa_fallback_quando_nome_nao_tem_base_ascii(self):
        resposta = self.criar("分類")

        self.assertEqual(resposta.status_code, 201)
        categoria_id = UUID(resposta.json()["id"])
        self.assertEqual(
            resposta.json()["slug"], f"categoria-{categoria_id.hex[:8]}"
        )

    def test_slug_longo_respeita_limite_e_preserva_sufixo_uuid(self):
        resposta = self.criar("Á" * 100)

        self.assertEqual(resposta.status_code, 201)
        corpo = resposta.json()
        categoria_id = UUID(corpo["id"])
        self.assertLessEqual(len(corpo["slug"]), 80)
        self.assertTrue(corpo["slug"].endswith(f"-{categoria_id.hex[:8]}"))

    def test_unicidade_por_owner_modo_e_soft_delete(self):
        primeira = self.criar("Ciência")
        self.assertEqual(primeira.status_code, 201)
        self.assertEqual(self.criar(" ciência ").status_code, 409)
        # SQLite não implementa lower Unicode como o PostgreSQL; a equivalência
        # CIÊNCIA/Ciência é coberta pelo teste de integração PostgreSQL real.
        self.assertEqual(self.criar("CIENCIA").status_code, 201)
        self.assertEqual(self.criar("Ciência", MODO_NEM_A_PATO).status_code, 201)
        app.dependency_overrides[usuario_atual] = lambda: self.outro
        self.assertEqual(self.criar("Ciência").status_code, 201)
        app.dependency_overrides[usuario_atual] = lambda: self.usuario
        self.assertEqual(
            self.client.delete(f"/api/v1/meu-conteudo/categorias/{primeira.json()['id']}").status_code,
            204,
        )
        self.assertEqual(self.criar("Ciência").status_code, 201)

    def test_quota_conta_ativas_e_inativas_e_delete_libera(self):
        ids = []
        for indice in range(10):
            resposta = self.criar(f"Categoria {indice}")
            self.assertEqual(resposta.status_code, 201)
            ids.append(resposta.json()["id"])
        self.client.patch(f"/api/v1/meu-conteudo/categorias/{ids[0]}", json={"ativa": False})
        self.assertEqual(self.criar("Excedente").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/meu-conteudo/categorias/{ids[0]}").status_code, 204)
        self.assertEqual(self.criar("Liberada").status_code, 201)

    def test_detalhe_oculta_oficial_outro_e_inexistente_mas_le_excluida(self):
        propria = self.categoria("Própria", excluida=True)
        outro = self.categoria("Outro", usuario=self.outro)
        oficial = self.categoria("Oficial", origem=ORIGEM_OFICIAL)
        self.assertEqual(self.client.get(f"/api/v1/meu-conteudo/categorias/{propria.id}").status_code, 200)
        for categoria_id in (outro.id, oficial.id, uuid4()):
            self.assertEqual(self.client.get(f"/api/v1/meu-conteudo/categorias/{categoria_id}").status_code, 404)

    def test_patch_campos_permitidos_slug_estavel_e_conflitos(self):
        primeira = self.categoria("Primeira", ativa=False)
        segunda = self.categoria("Segunda")
        resposta = self.client.patch(
            f"/api/v1/meu-conteudo/categorias/{primeira.id}",
            json={"nome": "Renomeada", "descricao": "  descrição  ", "ativa": True},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["slug"], primeira.slug)
        self.assertEqual(resposta.json()["descricao"], "descrição")
        self.assertTrue(resposta.json()["ativa"])
        self.assertEqual(self.client.patch(f"/api/v1/meu-conteudo/categorias/{primeira.id}", json={}).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/v1/meu-conteudo/categorias/{primeira.id}", json={"nome": " "}).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/v1/meu-conteudo/categorias/{primeira.id}", json={"modo": MODO_NEM_A_PATO}).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/v1/meu-conteudo/categorias/{primeira.id}", json={"nome": segunda.nome.lower()}).status_code, 409)
        excluida = self.categoria("Excluída", excluida=True)
        self.assertEqual(self.client.patch(f"/api/v1/meu-conteudo/categorias/{excluida.id}", json={"ativa": True}).status_code, 409)
        outro = self.categoria("Outro", usuario=self.outro)
        oficial = self.categoria("Oficial", origem=ORIGEM_OFICIAL)
        for categoria_id in (outro.id, oficial.id):
            self.assertEqual(self.client.patch(f"/api/v1/meu-conteudo/categorias/{categoria_id}", json={"nome": "X"}).status_code, 404)

    def test_patch_rejeita_cada_campo_imutavel_sem_alterar_categoria(self):
        categoria = self.categoria("Imutável")
        payloads = {
            "id": str(uuid4()),
            "slug": "slug-alterado",
            "modo": MODO_NEM_A_PATO,
            "origem": ORIGEM_OFICIAL,
            "usuario_id": str(self.outro.id),
            "criada_em": datetime.now(timezone.utc).isoformat(),
            "excluida_em": datetime.now(timezone.utc).isoformat(),
        }

        for campo, valor in payloads.items():
            with self.subTest(campo=campo):
                resposta = self.client.patch(
                    f"/api/v1/meu-conteudo/categorias/{categoria.id}",
                    json={campo: valor},
                )
                self.assertEqual(resposta.status_code, 422)

        with self.sessions() as db:
            preservada = db.get(Categoria, categoria.id)
            self.assertEqual(preservada.id, categoria.id)
            self.assertEqual(preservada.slug, categoria.slug)
            self.assertEqual(preservada.nome, categoria.nome)
            self.assertEqual(preservada.modo, categoria.modo)
            self.assertEqual(preservada.origem, categoria.origem)
            self.assertEqual(preservada.usuario_id, categoria.usuario_id)
            self.assertEqual(preservada.criada_em, categoria.criada_em)
            self.assertIsNone(preservada.excluida_em)

    def test_delete_bloqueia_pergunta_ativa_ou_inativa_em_cada_modo(self):
        for modo, ativa in (
            (MODO_QUIZ_CLASSICO, True), (MODO_QUIZ_CLASSICO, False),
            (MODO_NEM_A_PATO, True), (MODO_NEM_A_PATO, False),
        ):
            with self.subTest(modo=modo, ativa=ativa):
                categoria = self.categoria(f"{modo}-{ativa}", modo)
                with self.sessions() as db:
                    if modo == MODO_QUIZ_CLASSICO:
                        pergunta = Pergunta(
                            id=10000 + len(categoria.nome), categoria_id=categoria.id,
                            enunciado="Q", alternativa_a="A", alternativa_b="B",
                            alternativa_c="C", alternativa_d="D", alternativa_correta=0,
                            explicacao="E", origem=ORIGEM_USUARIO,
                            usuario_id=self.usuario.id, ativa=ativa,
                        )
                    else:
                        pergunta = PerguntaNemPato(
                            categoria_id=categoria.id, enunciado="Q", resposta_numerica=1,
                            explicacao="E", origem=ORIGEM_USUARIO,
                            usuario_id=self.usuario.id, ativa=ativa,
                        )
                    db.add(pergunta)
                    db.commit()
                self.assertEqual(self.client.delete(f"/api/v1/meu-conteudo/categorias/{categoria.id}").status_code, 409)

    def test_delete_ignora_pergunta_excluida_e_rejeita_repeticao_e_nao_owner(self):
        categoria = self.categoria("Livre")
        with self.sessions() as db:
            db.add(Pergunta(
                id=11000, categoria_id=categoria.id, enunciado="Q", alternativa_a="A",
                alternativa_b="B", alternativa_c="C", alternativa_d="D",
                alternativa_correta=0, explicacao="E", origem=ORIGEM_USUARIO,
                usuario_id=self.usuario.id, ativa=False,
                excluida_em=datetime.now(timezone.utc),
            ))
            db.commit()
        self.assertEqual(self.client.delete(f"/api/v1/meu-conteudo/categorias/{categoria.id}").status_code, 204)
        with self.sessions() as db:
            excluida = db.get(Categoria, categoria.id)
            self.assertFalse(excluida.ativa)
            self.assertIsNotNone(excluida.excluida_em)
            self.assertIsNotNone(excluida.atualizada_em)
        self.assertEqual(self.client.delete(f"/api/v1/meu-conteudo/categorias/{categoria.id}").status_code, 409)
        outro = self.categoria("Outro", usuario=self.outro)
        oficial = self.categoria("Oficial", origem=ORIGEM_OFICIAL)
        for categoria_id in (outro.id, oficial.id, uuid4()):
            self.assertEqual(self.client.delete(f"/api/v1/meu-conteudo/categorias/{categoria_id}").status_code, 404)

    def test_delete_ignora_pergunta_nem_pato_excluida_e_retorna_204_vazio(self):
        categoria = self.categoria("NP livre", MODO_NEM_A_PATO)
        with self.sessions() as db:
            db.add(PerguntaNemPato(
                categoria_id=categoria.id,
                enunciado="Excluída",
                resposta_numerica=10,
                explicacao="E",
                origem=ORIGEM_USUARIO,
                usuario_id=self.usuario.id,
                ativa=False,
                excluida_em=datetime.now(timezone.utc),
            ))
            db.commit()

        resposta = self.client.delete(
            f"/api/v1/meu-conteudo/categorias/{categoria.id}"
        )

        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(resposta.content, b"")

    def test_uuid_invalido_retorna_422(self):
        resposta = self.client.get(
            "/api/v1/meu-conteudo/categorias/nao-e-um-uuid"
        )

        self.assertEqual(resposta.status_code, 422)

    def test_catalogo_publico_continua_somente_oficial(self):
        privada = self.categoria("Privada")
        resposta = self.client.get("/api/v1/categorias")
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn(str(privada.id), [item["id"] for item in resposta.json()])


if __name__ == "__main__":
    unittest.main()
