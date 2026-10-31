import unittest
from datetime import date
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    AuditoriaAdministrativa, CatalogoOficial, Categoria,
    FontePerguntaNemPatoOficial, PerguntaNemPato, Usuario,
)
from app.services.reativacao_catalogos_oficiais import reativar_catalogo_oficial


class TestReativacaoCatalogosOficiais(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = Usuario(nome="Admin", email="admin-react@example.test", senha_hash="hash", perfil="ADMIN")
        self.categoria = Categoria(slug="macabro-react", nome="Macabro", modo="NEM_A_PATO", origem="OFICIAL", ativa=True)
        self.antigo = CatalogoOficial(catalogo_id="nem_incremental", versao=1, modo="NEM_A_PATO", status="ARQUIVADO", sha256="a" * 64)
        self.ativo = CatalogoOficial(catalogo_id="nem_incremental", versao=2, modo="NEM_A_PATO", status="ATIVO", sha256="b" * 64)
        self.db.add_all([self.admin, self.categoria, self.antigo, self.ativo]); self.db.flush()
        for indice in range(15):
            pergunta = PerguntaNemPato(
                categoria_id=self.categoria.id, enunciado=f"Pergunta {indice}?",
                resposta_numerica=indice, explicacao="Explicação verificável",
                origem="OFICIAL", ativa=True, catalogo_oficial_id=self.antigo.id,
                id_editorial=f"MAC-R-{indice:03d}",
            )
            pergunta.fontes_editoriais = [FontePerguntaNemPatoOficial(
                ordem=1, titulo="Fonte institucional", url="https://example.test/fonte",
                acessada_em=date(2026, 10, 31),
            )]
            self.db.add(pergunta)
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_reativa_incremental_preservando_perguntas_fontes_e_auditoria(self):
        ids = list(self.db.scalars(select(PerguntaNemPato.id).where(PerguntaNemPato.catalogo_oficial_id == self.antigo.id)))
        resposta = reativar_catalogo_oficial(self.db, self.antigo.id, self.ativo.id, self.admin, "Retorno editorial necessário")
        self.db.commit()
        self.assertEqual(resposta["perguntas_elegiveis"], 15)
        self.assertEqual(self.antigo.status, "ATIVO")
        self.assertEqual(self.ativo.status, "ARQUIVADO")
        self.assertEqual(ids, list(self.db.scalars(select(PerguntaNemPato.id).where(PerguntaNemPato.catalogo_oficial_id == self.antigo.id))))
        self.assertEqual(self.db.scalar(select(AuditoriaAdministrativa.operacao)), "REATIVAR_CATALOGO_OFICIAL")

    def test_rejeita_if_match_desatualizado_sem_alterar_estados(self):
        with self.assertRaises(HTTPException) as contexto:
            reativar_catalogo_oficial(self.db, self.antigo.id, self.antigo.id, self.admin, "Justificativa administrativa")
        self.assertEqual(contexto.exception.status_code, 412)
        self.db.rollback()
        self.assertEqual(self.antigo.status, "ARQUIVADO")
        self.assertEqual(self.ativo.status, "ATIVO")

    def test_rejeita_catalogo_abaixo_do_minimo(self):
        perguntas = list(self.db.scalars(select(PerguntaNemPato).where(PerguntaNemPato.catalogo_oficial_id == self.antigo.id)))
        for pergunta in perguntas[9:]:
            self.db.delete(pergunta)
        self.db.commit()
        with self.assertRaises(HTTPException) as contexto:
            reativar_catalogo_oficial(self.db, self.antigo.id, self.ativo.id, self.admin, "Justificativa administrativa")
        self.assertEqual(contexto.exception.status_code, 422)

    def test_rejeita_versao_inexistente_ou_ativa(self):
        with self.assertRaises(HTTPException) as inexistente:
            reativar_catalogo_oficial(self.db, uuid4(), self.ativo.id, self.admin, "Justificativa administrativa")
        self.assertEqual(inexistente.exception.status_code, 404)
        with self.assertRaises(HTTPException) as ativa:
            reativar_catalogo_oficial(self.db, self.ativo.id, self.ativo.id, self.admin, "Justificativa administrativa")
        self.assertEqual(ativa.exception.status_code, 409)

    def test_rejeita_ausencia_de_ativo_e_if_match_de_outro_modo(self):
        quiz = CatalogoOficial(catalogo_id="quiz-outro-modo", versao=1, modo="QUIZ_CLASSICO", status="ATIVO", sha256="c" * 64)
        self.db.add(quiz); self.db.commit()
        with self.assertRaises(HTTPException) as outro_modo:
            reativar_catalogo_oficial(self.db, self.antigo.id, quiz.id, self.admin, "Justificativa administrativa")
        self.assertEqual(outro_modo.exception.status_code, 412)
        self.ativo.status = "ARQUIVADO"; self.db.commit()
        with self.assertRaises(HTTPException) as ausente:
            reativar_catalogo_oficial(self.db, self.antigo.id, self.ativo.id, self.admin, "Justificativa administrativa")
        self.assertEqual(ausente.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
