import unittest
from datetime import date
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    AlteracaoRascunhoOficial, AuditoriaAdministrativa, CatalogoOficial,
    Categoria, FontePerguntaNemPatoOficial, FontePerguntaOficial, Pergunta,
    PerguntaNemPato, PerguntaNemPatoRascunho, PerguntaQuizRascunho, Usuario,
)
from app.services.rascunhos_catalogos_oficiais import criar_rascunho
from app.services.validacao_rascunhos_oficiais import (
    _detectar_duplicidades, validar_rascunho_oficial,
)


class TestValidacaoRascunhosOficiais(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False, autoflush=False)
        self.admin = Usuario(nome="Admin", email="validacao@example.com", senha_hash="hash", perfil="ADMIN")
        self.cat_quiz = Categoria(slug="geral", nome="Geral", modo="QUIZ_CLASSICO", origem="OFICIAL")
        self.cat_np = Categoria(slug="macabro", nome="Macabro", modo="NEM_A_PATO", origem="OFICIAL")
        self.quiz = CatalogoOficial(catalogo_id="quiz_v2", versao=2, modo="QUIZ_CLASSICO", status="ATIVO", sha256="a" * 64)
        self.np = CatalogoOficial(catalogo_id="np_v1", versao=1, modo="NEM_A_PATO", status="ATIVO", sha256="b" * 64)
        self.db.add_all([self.admin, self.cat_quiz, self.cat_np, self.quiz, self.np]); self.db.flush()
        quiz = Pergunta(id=1, categoria_id=self.cat_quiz.id, enunciado="Qual é a resposta documentada?", alternativa_a="Um", alternativa_b="Dois", alternativa_c="Três", alternativa_d="Quatro", alternativa_correta=1, explicacao="Explicação suficientemente completa para revisão estrutural.", dificuldade="FACIL", origem="OFICIAL", catalogo_oficial_id=self.quiz.id, id_editorial="GER-001")
        quiz.fontes_editoriais = [FontePerguntaOficial(ordem=1, titulo="Fonte institucional", url="https://example.org/quiz", acessada_em=date(2026, 1, 1))]
        np = PerguntaNemPato(categoria_id=self.cat_np.id, enunciado="Quantos registros foram documentados?", resposta_numerica=2**63 - 1, unidade="registros", explicacao="Explicação suficientemente completa para revisão estrutural.", origem="OFICIAL", catalogo_oficial_id=self.np.id, id_editorial="NP-001", tema_editorial="História", natureza_resposta="ESTIMATIVA", qualificacao_estimativa="Estimativa central para o período documentado")
        np.fontes_editoriais = [FontePerguntaNemPatoOficial(ordem=1, titulo="Fonte institucional", url="https://example.org/np", acessada_em=date(2026, 1, 2))]
        self.db.add_all([quiz, np]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_valida_quiz_sem_persistir_ou_mudar_revisao(self):
        rascunho = criar_rascunho(self.db, self.quiz.id, "Validação Quiz", self.admin); self.db.commit()
        antes = (rascunho.revisao, self.db.scalar(select(func.count(AlteracaoRascunhoOficial.id))), self.db.scalar(select(func.count(AuditoriaAdministrativa.id))))
        resultado = validar_rascunho_oficial(self.db, rascunho.id)
        depois = (rascunho.revisao, self.db.scalar(select(func.count(AlteracaoRascunhoOficial.id))), self.db.scalar(select(func.count(AuditoriaAdministrativa.id))))
        self.assertEqual(resultado["revisao_validada"], 1)
        self.assertEqual(resultado["resumo"]["perguntas_examinadas"], 1)
        self.assertEqual(resultado["resumo"]["erros"], 0)
        self.assertEqual(antes, depois)

    def test_detecta_regras_quiz_duplicidades_fontes_e_remocao(self):
        rascunho = criar_rascunho(self.db, self.quiz.id, "Inválido", self.admin); self.db.commit()
        item = self.db.scalar(select(PerguntaQuizRascunho).where(PerguntaQuizRascunho.rascunho_id == rascunho.id))
        item.alternativa_b = " um "
        item.alternativa_correta = 9
        item.explicacao = "Curta"
        item.fontes[0].url = "javascript:alert(1)"
        with self.db.no_autoflush:
            resultado = validar_rascunho_oficial(self.db, rascunho.id)
        codigos = {achado["codigo"] for achado in resultado["achados"]}
        self.assertTrue({"ALTERNATIVAS_EQUIVALENTES", "GABARITO_INVALIDO", "URL_FONTE_INVALIDA", "EXPLICACAO_CURTA"} <= codigos)
        self.assertGreaterEqual(resultado["resumo"]["erros"], 3)

    def test_detecta_enunciado_duplicado_e_semelhante_sem_alterar_itens(self):
        itens = [
            SimpleNamespace(id=UUID(int=1), id_editorial="GER-001", enunciado="Quantos registros foram documentados no evento histórico?"),
            SimpleNamespace(id=UUID(int=2), id_editorial="GER-002", enunciado="quantos registros foram documentados no evento historico"),
            SimpleNamespace(id=UUID(int=3), id_editorial="GER-003", enunciado="Quantos registros foram documentados no evento posterior?"),
        ]
        achados = []
        _detectar_duplicidades(itens, achados)
        codigos = {item["codigo"] for item in achados}
        self.assertIn("ENUNCIADO_DUPLICADO", codigos)
        self.assertIn("ENUNCIADO_SEMELHANTE", codigos)

    def test_preserva_bigint_e_exige_qualificacao_de_estimativa(self):
        rascunho = criar_rascunho(self.db, self.np.id, "Validação NP", self.admin); self.db.commit()
        item = self.db.scalar(select(PerguntaNemPatoRascunho).where(PerguntaNemPatoRascunho.rascunho_id == rascunho.id))
        resultado = validar_rascunho_oficial(self.db, rascunho.id)
        self.assertEqual(item.resposta_numerica, 2**63 - 1)
        self.assertEqual(resultado["resumo"]["erros"], 0)
        item.qualificacao_estimativa = None
        with self.db.no_autoflush:
            resultado = validar_rascunho_oficial(self.db, rascunho.id)
        self.assertIn("ESTIMATIVA_SEM_QUALIFICACAO", {a["codigo"] for a in resultado["achados"]})

    def test_rascunho_vazio_e_inexistente(self):
        rascunho = criar_rascunho(self.db, self.quiz.id, "Vazio", self.admin); self.db.commit()
        self.db.query(PerguntaQuizRascunho).filter_by(rascunho_id=rascunho.id).delete(); self.db.commit()
        resultado = validar_rascunho_oficial(self.db, rascunho.id)
        self.assertIn("RASCUNHO_SEM_PERGUNTAS", {a["codigo"] for a in resultado["achados"]})
        self.assertIsNone(validar_rascunho_oficial(self.db, UUID(int=0)))


if __name__ == "__main__":
    unittest.main()
