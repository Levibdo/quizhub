import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AchadoValidacaoRascunhoPersistido, CatalogoOficial,
    CatalogoOficialRascunho, Categoria, CicloRevisaoRascunho,
    FontePerguntaNemPatoRascunho, ItemRevisaoPergunta,
    PerguntaNemPatoRascunho, Usuario, VerificacaoFonteRevisao,
)
from app.security import JWT_COOKIE_NAME, criar_token_acesso, password_hash


class TestRevisaoEditorialHttp(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.env = patch.dict(os.environ, {"JWT_SECRET": "segredo-editorial-http-com-32-bytes"}); self.env.start()
        with self.factory.begin() as db:
            self.admin = Usuario(nome="Admin", email="admin-review@example.test", senha_hash=password_hash.hash("senha"), perfil="ADMIN")
            self.jogador = Usuario(nome="Jogador", email="player-review@example.test", senha_hash=password_hash.hash("senha"), perfil="JOGADOR")
            self.inativo = Usuario(nome="Inativo", email="inactive-review@example.test", senha_hash=password_hash.hash("senha"), perfil="ADMIN", ativo=False)
            categoria = Categoria(slug="macabro-http", nome="Macabro", modo="NEM_A_PATO", origem="OFICIAL")
            catalogo = CatalogoOficial(catalogo_id="np_http", versao=1, modo="NEM_A_PATO", status="ATIVO", sha256="f" * 64)
            db.add_all([self.admin, self.jogador, self.inativo, categoria, catalogo]); db.flush()
            self.rascunho = CatalogoOficialRascunho(catalogo_origem_id=catalogo.id, catalogo_id=catalogo.catalogo_id, modo="NEM_A_PATO", versao_base=1, numero_rascunho=1, nome="HTTP", criado_por_id=self.admin.id, modificado_por_id=self.admin.id)
            db.add(self.rascunho); db.flush()
            for i in range(100):
                p = PerguntaNemPatoRascunho(rascunho_id=self.rascunho.id, id_editorial=f"HTTP-{i:03}", categoria_id=categoria.id, categoria_slug_snapshot=categoria.slug, categoria_nome_snapshot=categoria.nome, ordem=i + 1, enunciado=f"Pergunta {i}?", resposta_numerica=i, unidade="itens", explicacao="Explicação documental suficientemente longa para validação.", tema_editorial="História", natureza_resposta="EXATA", ativa=True, tipo_alteracao="ADICIONADA", revisao=1, modificado_por_id=self.admin.id)
                p.fontes = [FontePerguntaNemPatoRascunho(ordem=1, titulo="Fonte", url=f"https://example.test/{i}", acessada_em=date(2026, 1, 1))]
                db.add(p)
        def banco():
            with self.factory() as db: yield db
        app.dependency_overrides[get_db] = banco
        self.factory_patch = patch("app.api.v1.admin.get_session_factory", return_value=self.factory); self.factory_patch.start()
        self.validator_patch = patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", side_effect=self._relatorio); self.validator_patch.start()
        self.client = TestClient(app)
        self.achados = []

    def tearDown(self):
        self.client.close(); app.dependency_overrides.clear(); self.validator_patch.stop(); self.factory_patch.stop(); self.env.stop(); self.engine.dispose()

    def _relatorio(self, db, rascunho_id):
        r = db.get(CatalogoOficialRascunho, rascunho_id)
        return {"rascunho_id": r.id, "revisao_validada": r.revisao, "resumo": {"perguntas_examinadas": 100, "perguntas_publicaveis": 100, "perguntas_validas_estruturalmente": 100, "perguntas_com_problemas": len(self.achados), "erros": 0, "avisos": len(self.achados), "informacoes": 0}, "achados": self.achados}

    def autenticar(self, usuario):
        self.client.cookies.clear(); self.client.cookies.set(JWT_COOKIE_NAME, criar_token_acesso(usuario.id, agora=datetime.now(timezone.utc)))

    def headers(self, chave, *, rev="1", editorial=None):
        csrf = self.client.get("/api/v1/admin/csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        h = {"Origin": "http://testserver", "X-CSRF-Token": csrf.json()["token"], "Idempotency-Key": chave, "If-Match": rev}
        if editorial is not None: h["X-Editorial-Revision"] = str(editorial)
        return h

    def test_autorizacao_consultas_e_escritas(self):
        base = f"/api/v1/admin/catalogos/rascunhos/{self.rascunho.id}"
        for caminho in (f"{base}/revisao", f"{base}/revisao/perguntas", f"{base}/revisao/avisos"):
            self.assertEqual(self.client.get(caminho).status_code, 401)
        self.autenticar(self.jogador)
        self.assertEqual(self.client.get(f"{base}/revisao").status_code, 403)
        self.autenticar(self.inativo)
        self.assertEqual(self.client.get(f"{base}/revisao").status_code, 401)
        self.autenticar(self.admin)
        self.assertEqual(self.client.get(f"{base}/revisao").status_code, 200)
        sem_csrf = self.client.post(f"{base}/encaminhar-revisao", headers={"Idempotency-Key": "x", "If-Match": "1"})
        self.assertEqual(sem_csrf.status_code, 403)
        sem_chave = self.client.post(f"{base}/encaminhar-revisao", headers={k: v for k, v in self.headers("temporaria").items() if k != "Idempotency-Key"})
        self.assertEqual(sem_chave.status_code, 428)
        sem_revisao = self.client.post(f"{base}/encaminhar-revisao", headers={k: v for k, v in self.headers("sem-revisao").items() if k != "If-Match"})
        self.assertEqual(sem_revisao.status_code, 428)

    def test_fluxo_http_idempotencia_e_contratos(self):
        self.autenticar(self.admin); base = f"/api/v1/admin/catalogos/rascunhos/{self.rascunho.id}"
        h = self.headers("encaminhar")
        resposta = self.client.post(f"{base}/encaminhar-revisao", headers=h)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        corpo = resposta.json(); self.assertEqual(corpo["status"], "EM_REVISAO"); self.assertEqual(corpo["revisao_editorial"], 1)
        replay = self.client.post(f"{base}/encaminhar-revisao", headers=h)
        self.assertEqual(replay.json(), corpo)
        conflito = self.client.post(f"{base}/encaminhar-revisao", headers={**h, "If-Match": "2"})
        self.assertEqual(conflito.status_code, 409)
        resumo = self.client.get(f"{base}/revisao"); self.assertEqual(resumo.status_code, 200); self.assertEqual(resumo.json()["contagens"]["PENDENTE"], 100)
        self.assertFalse(resumo.json()["elegivel_aprovacao"])
        self.assertIn("PERGUNTAS_ALTERADAS_NAO_APROVADAS", {x["codigo"] for x in resumo.json()["impedimentos_aprovacao"]})
        pagina = self.client.get(f"{base}/revisao/perguntas?limite=1"); self.assertEqual(pagina.status_code, 200)
        item = pagina.json()["itens"][0]; pergunta_id = UUID(item["pergunta_id"])
        with self.factory() as db:
            fonte_id = db.scalar(select(FontePerguntaNemPatoRascunho.id).where(FontePerguntaNemPatoRascunho.pergunta_rascunho_id == pergunta_id))
        detalhe = self.client.get(f"{base}/perguntas/{pergunta_id}")
        self.assertEqual(detalhe.status_code, 200, detalhe.text)
        self.assertEqual(detalhe.json()["referencias"][0]["id"], fonte_id)
        payload = {"decisao": "APROVADA", "justificativa": "Resposta conferida documentalmente na referência indicada.", "relacao_fontes_resposta": "Relação factual direta."}
        ausente = self.client.post(f"{base}/revisao/perguntas/{pergunta_id}/decisoes", json=payload, headers=self.headers("sem-editorial"))
        self.assertEqual(ausente.status_code, 428)
        hd = self.headers("decisao", editorial=1)
        decisao = self.client.post(f"{base}/revisao/perguntas/{pergunta_id}/decisoes", json=payload, headers=hd)
        self.assertEqual(decisao.status_code, 200, decisao.text); self.assertEqual(decisao.json()["estado"], "APROVADA")
        self.assertEqual(self.client.post(f"{base}/revisao/perguntas/{pergunta_id}/decisoes", json=payload, headers=hd).json(), decisao.json())
        obsoleta = self.client.post(f"{base}/revisao/perguntas/{pergunta_id}/decisoes", json={**payload, "justificativa": "Outra decisão concorrente suficientemente justificada."}, headers=self.headers("outra-decisao", editorial=1))
        self.assertEqual(obsoleta.status_code, 412)
        fonte_payload = {"resultado": "SUFICIENTE", "evidencia_documental": "Documento consultado e valor localizado na seção pertinente.", "relacao_com_resposta": "O documento declara explicitamente o valor do gabarito."}
        hf = self.headers("fonte", editorial=2)
        fonte = self.client.post(f"{base}/revisao/perguntas/{pergunta_id}/fontes/{fonte_id}/verificacoes", json=fonte_payload, headers=hf)
        self.assertEqual(fonte.status_code, 200, fonte.text)
        self.assertEqual(self.client.post(f"{base}/revisao/perguntas/{pergunta_id}/fontes/{fonte_id}/verificacoes", json=fonte_payload, headers=hf).json(), fonte.json())
        historico = self.client.get(f"{base}/revisao/perguntas/{pergunta_id}/historico")
        self.assertEqual(historico.status_code, 200); self.assertEqual(len(historico.json()["decisoes"]), 1); self.assertEqual(len(historico.json()["verificacoes_fontes"]), 1)
        invalida = self.client.post(f"{base}/revisao/perguntas/{pergunta_id}/fontes/{fonte_id}/verificacoes", json={"resultado": "SUFICIENTE", "evidencia_documental": "Documento consultado com evidência suficiente."}, headers=self.headers("fonte-invalida", editorial=3))
        self.assertEqual(invalida.status_code, 422)

    def test_aviso_correcao_e_devolucao(self):
        self.achados = [{"codigo":"EXPLICACAO_CURTA","nivel":"AVISO","pergunta_id":None,"id_editorial":None,"campo":"explicacao","mensagem":"Revisar explicação.","recomendacao":"Complementar."}]
        self.autenticar(self.admin); base=f"/api/v1/admin/catalogos/rascunhos/{self.rascunho.id}"
        ciclo=self.client.post(f"{base}/encaminhar-revisao",headers=self.headers("enc-aviso")).json()
        lista=self.client.get(f"{base}/revisao/avisos?estado=PENDENTE&severidade=AVISO&limite=1")
        self.assertEqual(lista.status_code,200,lista.text); self.assertEqual(lista.json()["total_pendencias"],1)
        self.assertIsNone(lista.json()["itens"][0]["decisao"])
        with self.factory() as db:
            ciclo_id=UUID(ciclo["ciclo_id"])
            achado=db.scalar(select(AchadoValidacaoRascunhoPersistido).where(AchadoValidacaoRascunhoPersistido.ciclo_id==ciclo_id))
            item=db.scalar(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id==ciclo_id))
        aviso=self.client.post(f"{base}/revisao/avisos/{achado.id}/decisao",json={"decisao":"ACEITO","justificativa":"Aviso avaliado e aceito com justificativa editorial."},headers=self.headers("aviso",editorial=1))
        self.assertEqual(aviso.status_code,200,aviso.text)
        tratados=self.client.get(f"{base}/revisao/avisos?estado=ACEITO")
        self.assertEqual(tratados.json()["total"],1); self.assertEqual(tratados.json()["total_pendencias"],0)
        self.assertEqual(tratados.json()["itens"][0]["ciclo_id"],ciclo["ciclo_id"])
        correcao=self.client.post(f"{base}/solicitar-correcao",json={"perguntas":[str(item.pergunta_nem_pato_id)],"justificativa":"A pergunta precisa de correção factual documentada."},headers=self.headers("corrigir",editorial=2))
        self.assertEqual(correcao.status_code,200,correcao.text); self.assertEqual(correcao.json()["status"],"EM_EDICAO")

    def test_aprovacao_reabertura_e_devolucao_geral(self):
        self.autenticar(self.admin); base=f"/api/v1/admin/catalogos/rascunhos/{self.rascunho.id}"
        inicio=self.client.post(f"{base}/encaminhar-revisao",headers=self.headers("enc-aprovar")).json()
        with self.factory.begin() as db:
            ciclo=db.get(CicloRevisaoRascunho,UUID(inicio["ciclo_id"])); itens=list(db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id==ciclo.id)))
            for item in itens:
                item.estado="APROVADA"; item.revisor_id=self.admin.id
                fonte=db.scalar(select(FontePerguntaNemPatoRascunho).where(FontePerguntaNemPatoRascunho.pergunta_rascunho_id==item.pergunta_nem_pato_id))
                db.add(VerificacaoFonteRevisao(item_id=item.id,fonte_nem_pato_id=fonte.id,fonte_titulo=fonte.titulo,fonte_url=fonte.url,fonte_acessada_em=str(fonte.acessada_em),fingerprint="a"*64,resultado="SUFICIENTE",evidencia_documental="Evidência documental conferida individualmente.",relacao_com_resposta="Relação direta com a resposta.",responsavel_id=self.admin.id))
        elegibilidade=self.client.get(f"{base}/revisao")
        self.assertEqual(elegibilidade.status_code,200,elegibilidade.text)
        self.assertTrue(elegibilidade.json()["elegivel_aprovacao"])
        self.assertTrue(elegibilidade.json()["exige_justificativa_autorrevisao"])
        self.assertEqual(elegibilidade.json()["impedimentos_aprovacao"],[])
        aprovar_resp=self.client.post(f"{base}/aprovar",json={"confirmacao_explicita":True,"justificativa_autorrevisao":"Autorrevisão justificada pela equipe reduzida e evidências individualizadas."},headers=self.headers("aprovar",editorial=1))
        self.assertEqual(aprovar_resp.status_code,200,aprovar_resp.text); self.assertEqual(aprovar_resp.json()["status"],"APROVADO")
        reabrir_resp=self.client.post(f"{base}/reabrir",json={"justificativa":"Nova evidência exige reabertura editorial controlada."},headers=self.headers("reabrir"))
        self.assertEqual(reabrir_resp.status_code,200,reabrir_resp.text); self.assertEqual(reabrir_resp.json()["status"],"EM_EDICAO")

        # Novo ciclo e devolução geral exercitam o endpoint sem alterar conteúdo.
        novo=self.client.post(f"{base}/encaminhar-revisao",headers=self.headers("enc-novo")).json()
        devolver=self.client.post(f"{base}/devolver-edicao",json={"justificativa":"Revisão geral devolvida para ajustes editoriais adicionais."},headers=self.headers("devolver",editorial=novo["revisao_editorial"]))
        self.assertEqual(devolver.status_code,200,devolver.text); self.assertEqual(devolver.json()["status"],"EM_EDICAO")


if __name__ == "__main__": unittest.main()
