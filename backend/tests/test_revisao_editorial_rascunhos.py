import unittest
from datetime import date
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    AprovacaoRascunho, CatalogoOficial, CatalogoOficialRascunho, Categoria,
    CicloRevisaoRascunho, DecisaoRevisaoPergunta,
    FontePerguntaNemPatoRascunho,
    ItemRevisaoPergunta, PerguntaNemPatoRascunho, Usuario,
    VerificacaoFonteRevisao,
)
from app.services.revisao_editorial_rascunhos import (
    aprovar, decidir_pergunta, encaminhar_revisao, reabrir, verificar_fonte,
)


class TestRevisaoEditorialRascunhos(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = Usuario(nome="Admin", email="review@example.com", senha_hash="hash", perfil="ADMIN")
        self.cat = Categoria(slug="macabro", nome="Macabro", modo="NEM_A_PATO", origem="OFICIAL")
        self.catalogo = CatalogoOficial(catalogo_id="np_v1", versao=1, modo="NEM_A_PATO", status="ATIVO", sha256="a" * 64)
        self.db.add_all([self.admin, self.cat, self.catalogo]); self.db.flush()
        self.rascunho = CatalogoOficialRascunho(catalogo_origem_id=self.catalogo.id, catalogo_id="np_v1", modo="NEM_A_PATO", versao_base=1, numero_rascunho=1, nome="Revisão", criado_por_id=self.admin.id, modificado_por_id=self.admin.id)
        self.db.add(self.rascunho); self.db.flush()
        for indice in range(100):
            pergunta = PerguntaNemPatoRascunho(rascunho_id=self.rascunho.id, id_editorial=f"NP-{indice:03}", categoria_id=self.cat.id, categoria_slug_snapshot=self.cat.slug, categoria_nome_snapshot=self.cat.nome, ordem=indice + 1, enunciado=f"Pergunta {indice}?", resposta_numerica=2**63 - 1 if indice == 0 else indice, unidade="itens", explicacao="Explicação factual suficientemente longa para a validação editorial.", tema_editorial="História", natureza_resposta="EXATA", ativa=True, tipo_alteracao="ADICIONADA", revisao=1, modificado_por_id=self.admin.id)
            pergunta.fontes = [FontePerguntaNemPatoRascunho(ordem=1, titulo="Fonte", url=f"https://example.org/{indice}", acessada_em=date(2026, 1, 1))]
            self.db.add(pergunta)
        self.db.commit()
        self.relatorio = {"rascunho_id": self.rascunho.id, "revisao_validada": 1, "resumo": {"perguntas_examinadas": 100, "perguntas_publicaveis": 100, "perguntas_validas_estruturalmente": 100, "perguntas_com_problemas": 0, "erros": 0, "avisos": 0, "informacoes": 0}, "achados": []}

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_fluxo_completo_preserva_bigint_e_invalida_aprovacao(self):
        with patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio):
            rascunho, ciclo = encaminhar_revisao(self.db, self.rascunho.id, 1, self.admin)
            self.assertEqual(rascunho.status, "EM_REVISAO")
            itens = list(self.db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id)))
            self.assertEqual(len(itens), 100)
            for item in itens:
                pergunta_id = item.pergunta_nem_pato_id
                fonte = self.db.scalar(select(FontePerguntaNemPatoRascunho).where(FontePerguntaNemPatoRascunho.pergunta_rascunho_id == pergunta_id))
                item, ciclo = verificar_fonte(self.db, rascunho.id, pergunta_id, fonte.id, 1, item.revisao_editorial, {"resultado": "SUFICIENTE", "evidencia_documental": "Documento consultado diretamente e número confirmado.", "relacao_com_resposta": "A referência declara explicitamente o valor usado na resposta.", "justificativa": None}, self.admin)
                item, ciclo = decidir_pergunta(self.db, rascunho.id, pergunta_id, 1, item.revisao_editorial, {"decisao": "APROVADA", "justificativa": "Gabarito e explicação conferidos contra a fonte.", "relacao_fontes_resposta": "Relação direta."}, self.admin)
            rascunho, ciclo, aprovacao = aprovar(self.db, rascunho.id, 1, ciclo.revisao_editorial, {"confirmacao_explicita": True, "justificativa_autorrevisao": "Autorrevisão necessária no ambiente atual, com evidências individualizadas."}, self.admin)
            self.assertEqual(rascunho.status, "APROVADO")
            self.assertTrue(aprovacao.valida)
            pergunta = self.db.get(PerguntaNemPatoRascunho, itens[0].pergunta_nem_pato_id)
            self.assertEqual(pergunta.resposta_numerica, 2**63 - 1)
            rascunho, ciclo = reabrir(self.db, rascunho.id, 1, "Correção editorial posterior devidamente justificada.", self.admin)
            self.assertEqual(rascunho.status, "EM_EDICAO")
            self.assertFalse(aprovacao.valida)
            self.assertEqual(ciclo.estado, "INVALIDADO")
            self.assertEqual(self.db.scalar(select(func.count(VerificacaoFonteRevisao.id))), 100)
            self.assertEqual(self.db.scalar(select(func.count(AprovacaoRascunho.id))), 1)

    def test_revisao_editorial_concorrente_e_lote_incremental(self):
        pergunta = self.db.scalar(select(PerguntaNemPatoRascunho).order_by(PerguntaNemPatoRascunho.ordem.desc()))
        pergunta.tipo_alteracao = "REMOVIDA"; self.db.commit()
        with patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio):
            _, ciclo = encaminhar_revisao(self.db, self.rascunho.id, 1, self.admin)
        self.assertEqual(self.db.scalar(select(func.count(ItemRevisaoPergunta.id)).where(ItemRevisaoPergunta.ciclo_id == ciclo.id)), 99)
        item = self.db.scalar(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id))
        decidir_pergunta(self.db, self.rascunho.id, item.pergunta_nem_pato_id, 1, 1, {"decisao": "REPROVADA", "justificativa": "Evidência insuficiente para confirmar a resposta.", "relacao_fontes_resposta": None}, self.admin)
        with self.assertRaises(HTTPException) as erro:
            decidir_pergunta(self.db, self.rascunho.id, item.pergunta_nem_pato_id, 1, 1, {"decisao": "APROVADA", "justificativa": "Tentativa concorrente com revisão obsoleta.", "relacao_fontes_resposta": None}, self.admin)
        self.assertEqual(erro.exception.status_code, 412)

    def test_falha_de_auditoria_reverte_decisao_e_revisoes(self):
        with patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio):
            _, ciclo = encaminhar_revisao(self.db, self.rascunho.id, 1, self.admin)
        self.db.commit()
        item = self.db.scalar(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id))
        with patch("app.services.revisao_editorial_rascunhos.registrar_auditoria_administrativa", side_effect=RuntimeError("falha de auditoria")):
            with self.assertRaisesRegex(RuntimeError, "falha de auditoria"):
                decidir_pergunta(self.db, self.rascunho.id, item.pergunta_nem_pato_id, 1, 1, {"decisao":"APROVADA","justificativa":"Decisão que deverá ser integralmente revertida.","relacao_fontes_resposta":None}, self.admin)
        self.db.rollback()
        item = self.db.get(ItemRevisaoPergunta, item.id)
        ciclo = self.db.get(CicloRevisaoRascunho, ciclo.id)
        self.assertEqual((item.estado, item.revisao_editorial, ciclo.revisao_editorial), ("PENDENTE", 1, 1))
        self.assertEqual(self.db.scalar(select(func.count(DecisaoRevisaoPergunta.id))), 0)

    def test_primeiro_lote_com_quinze_perguntas_e_aceito(self):
        perguntas = list(self.db.scalars(select(PerguntaNemPatoRascunho).order_by(PerguntaNemPatoRascunho.ordem)))
        for pergunta in perguntas[15:]:
            pergunta.tipo_alteracao = "REMOVIDA"
        self.db.commit()
        relatorio = dict(self.relatorio)
        relatorio["resumo"] = dict(self.relatorio["resumo"], perguntas_publicaveis=15)
        with patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=relatorio):
            _, ciclo = encaminhar_revisao(self.db, self.rascunho.id, 1, self.admin)
        itens = list(self.db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id == ciclo.id)))
        self.assertEqual(len(itens), 15)


if __name__ == "__main__":
    unittest.main()
