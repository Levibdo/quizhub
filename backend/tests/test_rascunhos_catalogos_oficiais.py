import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.db.base import Base
from app.models import (
    AlteracaoRascunhoOficial, AuditoriaAdministrativa, CatalogoOficial,
    Categoria, FontePerguntaNemPatoOficial, FontePerguntaOficial, Pergunta,
    PerguntaNemPato, PerguntaNemPatoRascunho, PerguntaQuizRascunho, Usuario,
)
from app.services.rascunhos_catalogos_oficiais import (
    adicionar_pergunta, alterar_remocao, criar_rascunho, descartar_rascunho,
    salvar_pergunta,
)


class TestRascunhosCatalogosOficiais(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = Usuario(nome="Admin", email="draft@example.com", senha_hash="hash", perfil="ADMIN")
        self.cat_quiz = Categoria(slug="geral", nome="Geral", modo="QUIZ_CLASSICO", origem="OFICIAL")
        self.cat_np = Categoria(slug="macabro", nome="Macabro", modo="NEM_A_PATO", origem="OFICIAL")
        self.quiz = CatalogoOficial(catalogo_id="quiz_v2", versao=2, modo="QUIZ_CLASSICO", status="ATIVO", sha256="a" * 64)
        self.np = CatalogoOficial(catalogo_id="np_v1", versao=1, modo="NEM_A_PATO", status="ATIVO", sha256="b" * 64)
        self.db.add_all([self.admin, self.cat_quiz, self.cat_np, self.quiz, self.np]); self.db.flush()
        q = Pergunta(id=1, categoria_id=self.cat_quiz.id, enunciado="Original?", alternativa_a="A", alternativa_b="B", alternativa_c="C", alternativa_d="D", alternativa_correta=0, explicacao="Explicação", dificuldade="FACIL", origem="OFICIAL", catalogo_oficial_id=self.quiz.id, id_editorial="GER-001")
        q.fontes_editoriais = [FontePerguntaOficial(ordem=1, titulo="Fonte", url="https://example.org/q", acessada_em=date(2026, 1, 1))]
        n = PerguntaNemPato(categoria_id=self.cat_np.id, enunciado="Quantidade?", resposta_numerica=2**63 - 1, unidade="itens", explicacao="Explicação NP", origem="OFICIAL", catalogo_oficial_id=self.np.id, id_editorial="NP-001", natureza_resposta="EXATA")
        n.fontes_editoriais = [FontePerguntaNemPatoOficial(ordem=1, titulo="Fonte NP", url="https://example.org/np", acessada_em=date(2026, 1, 2))]
        self.db.add_all([q, n]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_clona_isoladamente_perguntas_fontes_e_bigint(self):
        rq = criar_rascunho(self.db, self.quiz.id, "Revisão Quiz", self.admin)
        rn = criar_rascunho(self.db, self.np.id, "Revisão NP", self.admin)
        self.db.commit()
        cq = self.db.scalar(select(PerguntaQuizRascunho).where(PerguntaQuizRascunho.rascunho_id == rq.id))
        cn = self.db.scalar(select(PerguntaNemPatoRascunho).where(PerguntaNemPatoRascunho.rascunho_id == rn.id))
        self.assertEqual(cq.fontes[0].url, "https://example.org/q")
        self.assertEqual(cn.fontes[0].url, "https://example.org/np")
        self.assertEqual(cn.resposta_numerica, 2**63 - 1)
        self.assertEqual(self.db.scalar(select(func.count(Pergunta.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(PerguntaNemPato.id))), 1)

    def test_edita_adiciona_remove_restaura_descarta_e_audita(self):
        r = criar_rascunho(self.db, self.quiz.id, "Rascunho", self.admin); self.db.commit()
        item = self.db.scalar(select(PerguntaQuizRascunho).where(PerguntaQuizRascunho.rascunho_id == r.id))
        payload = {"id_editorial": item.id_editorial, "categoria_id": self.cat_quiz.id, "enunciado": "Editada?", "alternativas": ["A1", "B1", "C1", "D1"], "alternativa_correta": 1, "explicacao": "Nova explicação", "dificuldade": "MEDIA", "ativa": True, "referencias": [{"titulo": "Nova", "url": "https://example.org/nova", "acessada_em": date(2026, 2, 1)}]}
        _, rev = salvar_pergunta(self.db, r.id, item.id, payload, self.admin, 1)
        payload_nova = payload | {"id_editorial": "GER-002", "enunciado": "Nova?"}
        nova, rev = adicionar_pergunta(self.db, r.id, payload_nova, self.admin, rev)
        _, rev = alterar_remocao(self.db, r.id, nova.id, self.admin, rev, restaurar=False)
        _, rev = alterar_remocao(self.db, r.id, nova.id, self.admin, rev, restaurar=True)
        r = descartar_rascunho(self.db, r.id, "Encerrado", self.admin, rev)
        self.db.commit()
        self.assertEqual(r.status, "DESCARTADO")
        self.assertEqual(nova.tipo_alteracao, "ADICIONADA")
        self.assertEqual(self.db.scalar(select(func.count(AlteracaoRascunhoOficial.id))), 6)
        self.assertEqual(self.db.scalar(select(func.count(AuditoriaAdministrativa.id))), 6)
        self.assertEqual(self.db.get(Pergunta, 1).enunciado, "Original?")

    def test_revisao_divergente_e_estado_descartado_bloqueiam_escrita(self):
        r = criar_rascunho(self.db, self.quiz.id, "Rascunho", self.admin); self.db.commit()
        item = self.db.scalar(select(PerguntaQuizRascunho).where(PerguntaQuizRascunho.rascunho_id == r.id))
        with self.assertRaises(HTTPException) as erro:
            alterar_remocao(self.db, r.id, item.id, self.admin, 99, restaurar=False)
        self.assertEqual(erro.exception.status_code, 412); self.db.rollback()
        descartar_rascunho(self.db, r.id, "Fim", self.admin, 1); self.db.commit()
        with self.assertRaises(HTTPException) as erro:
            alterar_remocao(self.db, r.id, item.id, self.admin, 2, restaurar=False)
        self.assertEqual(erro.exception.status_code, 409)

    def test_falha_de_auditoria_permite_rollback_integral(self):
        with patch(
            "app.services.rascunhos_catalogos_oficiais.registrar_auditoria_administrativa",
            side_effect=RuntimeError("falha sintética de auditoria"),
        ):
            with self.assertRaisesRegex(RuntimeError, "falha sintética"):
                criar_rascunho(self.db, self.quiz.id, "Não persiste", self.admin)
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(func.count(PerguntaQuizRascunho.id))), 0)
        from app.models import CatalogoOficialRascunho
        self.assertEqual(self.db.scalar(select(func.count(CatalogoOficialRascunho.id))), 0)


if __name__ == "__main__":
    unittest.main()
