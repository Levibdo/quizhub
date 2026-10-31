import os
import unittest
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401 — inicializa o registro dos modelos
from app.models import (
    AlteracaoRascunhoOficial, AuditoriaAdministrativa, CatalogoOficial,
    Categoria, FontePerguntaNemPatoOficial, FontePerguntaOficial, Pergunta,
    PerguntaNemPato, Usuario,
)
from app.services.rascunhos_catalogos_oficiais import criar_rascunho
from app.services.validacao_rascunhos_oficiais import validar_rascunho_oficial

URL_ENV = "C41_TEST_DATABASE_URL"
NAME_ENV = "C41_TEST_DATABASE_NAME"
DATABASE_URL = os.getenv(URL_ENV, "").strip()
AUTHORIZED = os.getenv(NAME_ENV, "").strip()


@unittest.skipUnless(DATABASE_URL and AUTHORIZED, f"configure {URL_ENV} e {NAME_ENV}")
class TestC41Postgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(DATABASE_URL)
        if url.get_backend_name() != "postgresql" or url.database != AUTHORIZED or not AUTHORIZED.startswith("quizhub_c41_test_"):
            raise RuntimeError("C4.1 exige PostgreSQL descartável nomeado quizhub_c41_test_*")
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with cls.engine.connect() as conexao:
            revisao = conexao.scalar(text("SELECT version_num FROM alembic_version"))
            if revisao != "0020":
                raise RuntimeError(f"revisão descartável esperada 0020, encontrada {revisao}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_dois_modos_e_leitura_sem_efeitos_colaterais(self):
        with Session(self.engine, expire_on_commit=False) as db:
            admin = Usuario(nome="Admin C41", email=f"c41-{uuid4()}@example.test", senha_hash="hash", perfil="ADMIN")
            cq = Categoria(slug=f"geral-{uuid4().hex[:8]}", nome="Geral C41", modo="QUIZ_CLASSICO", origem="OFICIAL")
            cn = Categoria(slug=f"macabro-{uuid4().hex[:8]}", nome="Macabro C41", modo="NEM_A_PATO", origem="OFICIAL")
            catalogo_q = CatalogoOficial(catalogo_id=f"quiz-c41-{uuid4().hex[:8]}", versao=1, modo="QUIZ_CLASSICO", status="PREPARADO", sha256="a" * 64)
            catalogo_n = CatalogoOficial(catalogo_id=f"np-c41-{uuid4().hex[:8]}", versao=1, modo="NEM_A_PATO", status="PREPARADO", sha256="b" * 64)
            db.add_all([admin, cq, cn, catalogo_q, catalogo_n]); db.flush()
            q = Pergunta(id=910001, categoria_id=cq.id, enunciado="Pergunta estrutural clássica?", alternativa_a="A", alternativa_b="B", alternativa_c="C", alternativa_d="D", alternativa_correta=0, explicacao="Explicação suficientemente completa para a validação automática.", dificuldade="MEDIA", origem="OFICIAL", catalogo_oficial_id=catalogo_q.id, id_editorial=f"Q-{uuid4().hex[:8]}")
            q.fontes_editoriais = [FontePerguntaOficial(ordem=1, titulo="Fonte C41", url="https://example.org/c41/quiz", acessada_em=date(2026, 10, 23))]
            n = PerguntaNemPato(categoria_id=cn.id, enunciado="Quantos registros existem?", resposta_numerica=2**63 - 1, unidade="registros", explicacao="Explicação suficientemente completa para a validação automática.", origem="OFICIAL", catalogo_oficial_id=catalogo_n.id, id_editorial=f"N-{uuid4().hex[:8]}", tema_editorial="História", natureza_resposta="ESTIMATIVA", qualificacao_estimativa="Estimativa central do período documentado")
            n.fontes_editoriais = [FontePerguntaNemPatoOficial(ordem=1, titulo="Fonte C41", url="https://example.org/c41/np", acessada_em=date(2026, 10, 23))]
            db.add_all([q, n]); db.flush()
            rq = criar_rascunho(db, catalogo_q.id, "Quiz C41", admin)
            rn = criar_rascunho(db, catalogo_n.id, "NP C41", admin)
            db.commit()

            antes = (
                rq.revisao, rn.revisao,
                db.scalar(select(func.count(Pergunta.id))), db.scalar(select(func.count(PerguntaNemPato.id))),
                db.scalar(select(func.count(AlteracaoRascunhoOficial.id))), db.scalar(select(func.count(AuditoriaAdministrativa.id))),
            )
            quiz = validar_rascunho_oficial(db, rq.id)
            np = validar_rascunho_oficial(db, rn.id)
            depois = (
                rq.revisao, rn.revisao,
                db.scalar(select(func.count(Pergunta.id))), db.scalar(select(func.count(PerguntaNemPato.id))),
                db.scalar(select(func.count(AlteracaoRascunhoOficial.id))), db.scalar(select(func.count(AuditoriaAdministrativa.id))),
            )
            self.assertEqual(quiz["resumo"]["erros"], 0)
            self.assertEqual(np["resumo"]["erros"], 0)
            self.assertEqual(np["resumo"]["perguntas_validas_estruturalmente"], 1)
            self.assertEqual(antes, depois)
            db.rollback()


if __name__ == "__main__":
    unittest.main()
