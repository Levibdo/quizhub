import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli import main as cli_main
from app.db.base import Base
from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app
from app.models import Categoria
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
                (item.id, item.nome, item.descricao, item.ativa)
                for item in session.scalars(
                    select(Categoria).order_by(Categoria.id)
                )
            ]


class TestCategoriasService(CategoriasTestCase):
    def test_listagem_ativa_e_ordenacao_deterministica(self):
        with self.sessions() as session:
            session.get(Categoria, "geral").ativa = False
            session.commit()
            categorias = CategoriasService.listar(session, somente_ativas=True)
        self.assertEqual(
            [(item.nome, item.id) for item in categorias],
            [("Matemática", "matematica"), ("Tecnologia", "tecnologia")],
        )

    def test_criacao_normaliza_campos_e_preserva_existentes(self):
        antes = self.categorias()
        with self.sessions() as session:
            criada = CategoriasService.criar(
                session, " ciencias-naturais ", " Ciências Naturais ", "  Vida e matéria.  "
            )
            self.assertEqual(
                (criada.id, criada.nome, criada.descricao, criada.ativa),
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
            session.get(Categoria, "geral").ativa = False
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
                        "id": "matematica",
                        "nome": "Matemática",
                        "descricao": "Conceitos básicos de matemática.",
                    },
                    {
                        "id": "tecnologia",
                        "nome": "Tecnologia",
                        "descricao": "Fundamentos de tecnologia.",
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
            self.assertEqual(session.get(Categoria, "ciencias").nome, "Ciências")

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
