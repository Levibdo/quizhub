import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli import main as cli_main
from app.db.base import Base
from app.db.seed import seed_database
from app.conteudo import (
    CATEGORIAS_OFICIAIS,
    MODO_NEM_A_PATO,
    MODO_QUIZ_CLASSICO,
    ORIGEM_OFICIAL,
    ORIGEM_USUARIO,
)
from app.db.session import get_db
from app.main import app
from app.models import Categoria, Usuario
from app.services.categorias import (
    CategoriaDuplicada,
    CategoriaInvalida,
    CategoriasService,
)


class CategoriasTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            seed_database(session)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def categorias(self):
        with self.sessions() as session:
            return [
                (item.slug, item.nome, item.descricao, item.ativa)
                for item in session.scalars(
                    select(Categoria).order_by(Categoria.id)
                )
            ]


class TestCategoriasService(CategoriasTestCase):
    def test_catalogo_oficial_tem_uuid_modo_e_origem_exatos(self):
        with self.sessions() as session:
            encontradas = {
                (item.modo, item.slug): (item.id, item.origem, item.usuario_id)
                for item in session.scalars(select(Categoria))
            }
            for modo, categorias in CATEGORIAS_OFICIAIS.items():
                for slug, categoria_id in categorias.items():
                    if modo == MODO_NEM_A_PATO:
                        session.add(Categoria(
                            id=categoria_id,
                            slug=slug,
                            nome=slug.title(),
                            modo=modo,
                            origem=ORIGEM_OFICIAL,
                        ))
                        encontradas[(modo, slug)] = (
                            categoria_id,
                            ORIGEM_OFICIAL,
                            None,
                        )
            session.flush()

        self.assertEqual(len(encontradas), 8)
        for modo, categorias in CATEGORIAS_OFICIAIS.items():
            for slug, categoria_id in categorias.items():
                self.assertEqual(
                    encontradas[(modo, slug)],
                    (categoria_id, ORIGEM_OFICIAL, None),
                )

    def test_categoria_usuario_respeita_owner_soft_delete_e_unicidade_do_nome(self):
        usuario_a = Usuario(
            id=uuid4(), nome="A", email="a-categoria@example.com", senha_hash="hash"
        )
        usuario_b = Usuario(
            id=uuid4(), nome="B", email="b-categoria@example.com", senha_hash="hash"
        )
        usuario_a_id = usuario_a.id
        usuario_b_id = usuario_b.id
        with self.sessions() as session:
            session.add_all((usuario_a, usuario_b))
            session.commit()
            session.add_all((
                Categoria(
                    slug="curiosidades-a",
                    nome="Curiosidades",
                    modo=MODO_QUIZ_CLASSICO,
                    origem=ORIGEM_USUARIO,
                    usuario_id=usuario_a_id,
                ),
                Categoria(
                    slug="curiosidades-b",
                    nome="Curiosidades",
                    modo=MODO_QUIZ_CLASSICO,
                    origem=ORIGEM_USUARIO,
                    usuario_id=usuario_b_id,
                ),
                Categoria(
                    slug="curiosidades-nem",
                    nome="Curiosidades",
                    modo=MODO_NEM_A_PATO,
                    origem=ORIGEM_USUARIO,
                    usuario_id=usuario_a_id,
                ),
            ))
            session.commit()
            session.add(Categoria(
                slug="duplicada",
                nome="CURIOSIDADES",
                modo=MODO_QUIZ_CLASSICO,
                origem=ORIGEM_USUARIO,
                usuario_id=usuario_a_id,
            ))
            with self.assertRaises(IntegrityError):
                session.commit()

        casos_invalidos = (
            Categoria(
                slug="sem-owner", nome="Sem owner", modo=MODO_QUIZ_CLASSICO,
                origem=ORIGEM_USUARIO,
            ),
            Categoria(
                slug="oficial-com-owner", nome="Oficial owner",
                modo=MODO_QUIZ_CLASSICO, origem=ORIGEM_OFICIAL,
                usuario_id=usuario_a_id,
            ),
            Categoria(
                slug="oficial-excluida", nome="Oficial excluída",
                modo=MODO_QUIZ_CLASSICO, origem=ORIGEM_OFICIAL,
                ativa=False, excluida_em=datetime(2026, 10, 4, 12, tzinfo=timezone.utc),
            ),
        )
        for categoria in casos_invalidos:
            with self.subTest(slug=categoria.slug), self.sessions() as session:
                session.add(categoria)
                with self.assertRaises((IntegrityError, TypeError)):
                    session.commit()

    def test_listagem_ativa_e_ordenacao_deterministica(self):
        with self.sessions() as session:
            session.get(Categoria, CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["geral"]).ativa = False
            session.commit()
            categorias = CategoriasService.listar(session, somente_ativas=True)
        self.assertEqual(
            [(item.nome, item.slug) for item in categorias],
            [
                ("Entretenimento", "entretenimento"),
                ("Matemática", "matematica"),
                ("Tecnologia", "tecnologia"),
            ],
        )

    def test_criacao_normaliza_campos_e_preserva_existentes(self):
        antes = self.categorias()
        with self.sessions() as session:
            criada = CategoriasService.criar(
                session, " ciencias-naturais ", " Ciências Naturais ", "  Vida e matéria.  "
            )
            self.assertEqual(
                (criada.slug, criada.nome, criada.descricao, criada.ativa),
                ("ciencias-naturais", "Ciências Naturais", "Vida e matéria.", True),
            )
        atuais = [item for item in self.categorias() if item[0] != "ciencias-naturais"]
        self.assertEqual(atuais, antes)

    def test_id_duplicado_nao_altera_categoria_existente(self):
        antes = self.categorias()
        with self.sessions() as session:
            with self.assertRaisesRegex(CategoriaDuplicada, "já existe"):
                CategoriasService.criar(session, " geral ", "Outro nome")
        self.assertEqual(self.categorias(), antes)

    def test_campos_obrigatorios_e_regra_do_id(self):
        casos = (
            ("", "Nome", "código/id é obrigatório"),
            ("valido", " ", "nome é obrigatório"),
            ("Código Inválido", "Nome", "letras minúsculas"),
            ("-invalido", "Nome", "letras minúsculas"),
        )
        for codigo, nome, mensagem in casos:
            with self.subTest(codigo=codigo, nome=nome):
                with self.sessions() as session:
                    with self.assertRaisesRegex(CategoriaInvalida, mensagem):
                        CategoriasService.criar(session, codigo, nome)


class TestCategoriasApi(CategoriasTestCase):
    def test_endpoint_publico_retorna_apenas_ativas_ordenadas(self):
        with self.sessions() as session:
            session.get(Categoria, CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["geral"]).ativa = False
            usuario = Usuario(
                nome="Dona do conteúdo",
                email="privada-catalogo@example.com",
                senha_hash="hash",
            )
            session.add(usuario)
            session.flush()
            session.add(Categoria(
                slug="privada-ativa",
                nome="Privada ativa",
                modo=MODO_QUIZ_CLASSICO,
                origem=ORIGEM_USUARIO,
                usuario_id=usuario.id,
                ativa=True,
            ))
            session.commit()

        def banco_teste():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = banco_teste
        with TestClient(app) as client:
            resposta = client.get("/api/v1/categorias")
            self.assertEqual(resposta.status_code, 200, resposta.text)
            self.assertEqual(
                resposta.json(),
                [
                    {
                        "id": str(CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["entretenimento"]),
                        "slug": "entretenimento",
                        "nome": "Entretenimento",
                        "descricao": "Cinema, música, televisão e cultura.",
                        "modo": MODO_QUIZ_CLASSICO,
                        "origem": "OFICIAL",
                    },
                    {
                        "id": str(CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["matematica"]),
                        "slug": "matematica",
                        "nome": "Matemática",
                        "descricao": "Conceitos básicos de matemática.",
                        "modo": MODO_QUIZ_CLASSICO,
                        "origem": "OFICIAL",
                    },
                    {
                        "id": str(CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"]),
                        "slug": "tecnologia",
                        "nome": "Tecnologia",
                        "descricao": "Fundamentos de tecnologia.",
                        "modo": MODO_QUIZ_CLASSICO,
                        "origem": "OFICIAL",
                    },
                ],
            )
            self.assertEqual(client.post("/api/v1/categorias").status_code, 405)


class TestCategoriasCli(CategoriasTestCase):
    def executar(self, argumentos, respostas=()):
        entradas = iter(respostas)
        saidas = []
        codigo = cli_main(
            argumentos,
            input_fn=lambda _prompt: next(entradas),
            output=saidas.append,
            session_factory=self.sessions,
        )
        return codigo, saidas

    def test_listar_exibe_status_sem_alterar_banco(self):
        antes = self.categorias()
        codigo, saidas = self.executar(["categoria", "listar"])
        self.assertEqual(codigo, 0)
        self.assertEqual(self.categorias(), antes)
        self.assertTrue(any("geral | Geral" in linha and "ativa" in linha for linha in saidas))

    def test_criar_persiste_somente_apos_confirmacao(self):
        codigo, saidas = self.executar(
            ["categoria", "criar"],
            ("  Ciências  ", " ciencias ", "  Perguntas científicas. ", "sim"),
        )
        self.assertEqual(codigo, 0)
        self.assertTrue(any("criada com sucesso" in linha for linha in saidas))
        with self.sessions() as session:
            self.assertEqual(session.scalar(select(Categoria).where(Categoria.slug == "ciencias")).nome, "Ciências")

    def test_cancelar_nao_persiste(self):
        antes = self.categorias()
        codigo, saidas = self.executar(
            ["categoria", "criar"], ("Nova", "nova", "", "n")
        )
        self.assertEqual(codigo, 0)
        self.assertEqual(self.categorias(), antes)
        self.assertTrue(any("cancelada" in linha for linha in saidas))

    def test_duplicidade_exibe_mensagem_compreensivel(self):
        codigo, saidas = self.executar(
            ["categoria", "criar"], ("Outra", "geral", "", "s")
        )
        self.assertEqual(codigo, 1)
        self.assertTrue(any("já existe" in linha for linha in saidas))


if __name__ == "__main__":
    unittest.main()
