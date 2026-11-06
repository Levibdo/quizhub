import unittest
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    CatalogoOficial, Categoria, CategoriaOficialRascunho,
    CatalogoOficialRascunho, PerguntaNemPatoRascunho, Usuario,
)
from app.services.categorias_oficiais_rascunhos import alterar_remocao_categoria, salvar_categoria
from app.services.importacao_catalogo_oficial_json import confirmar, previsualizar
from app.services.rascunhos_catalogos_oficiais import criar_rascunho


class TestCategoriasVersionadasEImportacaoJson(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = Usuario(nome="Admin", email="categorias@example.test", senha_hash="hash", perfil="ADMIN")
        self.catalogo = CatalogoOficial(catalogo_id="np_json", versao=1, modo="NEM_A_PATO", status="ATIVO", sha256="0" * 64)
        self.db.add_all([self.admin, self.catalogo]); self.db.flush()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_categoria_nova_reserva_identidade_inativa_e_exige_revisao(self):
        rascunho = criar_rascunho(self.db, self.catalogo.id, "Categorias", self.admin)
        item, revisao = salvar_categoria(self.db, rascunho.id, None, {
            "slug": "historia", "nome": "História", "descricao": "Eventos", "ativa": True,
        }, 1, self.admin)
        identidade = self.db.get(Categoria, item.categoria_id)
        self.assertFalse(identidade.ativa)
        self.assertEqual((item.tipo_alteracao, revisao), ("ADICIONADA", 2))
        with self.assertRaises(Exception) as contexto:
            salvar_categoria(self.db, rascunho.id, item.categoria_id, {
                "slug": "historia", "nome": "História mundial", "descricao": None, "ativa": True,
            }, 1, self.admin)
        self.assertEqual(contexto.exception.status_code, 412)

    def test_importacao_json_cria_rascunho_sem_publicar(self):
        conteudo = {
            "nome_rascunho": "Importação sintética",
            "modo": "NEM_A_PATO",
            "categorias": [{"slug": "historia", "nome": "História", "descricao": None, "ativa": True}],
            "perguntas_quiz": [],
            "perguntas_nem_pato": [{
                "id_editorial": "SYN-JSON-001", "categoria_slug": "historia",
                "enunciado": "Quantos itens sintéticos?", "resposta_numerica": "42",
                "unidade": "itens", "explicacao": "Explicação exclusivamente sintética.",
                "natureza_resposta": "EXATA", "tema_editorial": "Teste",
                "qualificacao_estimativa": None,
                "referencias": [{"titulo": "Fonte sintética", "url": "https://example.invalid/fonte", "acessada_em": date(2026, 1, 1)}],
            }],
        }
        previa = previsualizar(conteudo)
        rascunho, revisao, resultado = confirmar(
            self.db, self.catalogo.id, conteudo, previa["sha256"], self.admin
        )
        self.db.flush()
        self.assertEqual(rascunho.status, "EM_EDICAO")
        self.assertFalse(resultado["publicacao_automatica"])
        self.assertGreater(revisao, 1)
        self.assertEqual(len(list(self.db.scalars(select(CategoriaOficialRascunho).where(CategoriaOficialRascunho.rascunho_id == rascunho.id)))), 1)
        pergunta = self.db.scalar(select(PerguntaNemPatoRascunho).where(PerguntaNemPatoRascunho.rascunho_id == rascunho.id))
        self.assertEqual((pergunta.id_editorial, pergunta.resposta_numerica), ("SYN-JSON-001", 42))
        self.assertIsNone(rascunho.catalogo_publicado_id)

    def test_remocao_e_restauracao_sao_logicas_e_versionadas(self):
        rascunho = criar_rascunho(self.db, self.catalogo.id, "Categorias", self.admin)
        item, revisao = salvar_categoria(self.db, rascunho.id, None, {
            "slug": "historia", "nome": "História", "descricao": None, "ativa": True,
        }, rascunho.revisao, self.admin)
        identidade_id = item.categoria_id
        item, revisao = alterar_remocao_categoria(
            self.db, rascunho.id, identidade_id, revisao, self.admin, restaurar=False,
        )
        self.assertEqual(item.tipo_alteracao, "REMOVIDA")
        self.assertIsNotNone(self.db.get(Categoria, identidade_id))
        item, revisao = alterar_remocao_categoria(
            self.db, rascunho.id, identidade_id, revisao, self.admin, restaurar=True,
        )
        self.assertEqual(item.tipo_alteracao, "ADICIONADA")
        self.assertEqual(rascunho.revisao, revisao)

    def test_previsualizacao_individualiza_categoria_ausente(self):
        conteudo = {
            "nome_rascunho": "Inválida", "modo": "NEM_A_PATO",
            "categorias": [{"slug": "historia", "nome": "História", "descricao": None, "ativa": True}],
            "perguntas_quiz": [],
            "perguntas_nem_pato": [{"categoria_slug": "outra"}],
        }
        resultado = previsualizar(conteudo)
        self.assertFalse(resultado["valido"])
        self.assertEqual(resultado["erros"][0], {"registro": 0, "campo": "categoria_slug", "codigo": "CATEGORIA_AUSENTE"})


if __name__ == "__main__":
    unittest.main()
