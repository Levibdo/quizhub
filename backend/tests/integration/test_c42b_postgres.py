import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401 — inicializa todos os modelos
from app.models import (
    AprovacaoRascunho, CatalogoOficial, CatalogoOficialRascunho, Categoria,
    CicloRevisaoRascunho, FontePerguntaNemPatoRascunho,
    FontePerguntaNemPatoOficial, FontePerguntaOficial, ItemRevisaoPergunta,
    Partida, Pergunta, PerguntaNemPato, PerguntaNemPatoRascunho, Temporada,
    Usuario,
    VerificacaoFonteRevisao,
)
from app.services.revisao_editorial_rascunhos import (
    aprovar, decidir_pergunta, devolver_edicao, encaminhar_revisao, reabrir,
    verificar_fonte,
)

URL = os.getenv("C42B_TEST_DATABASE_URL", "").strip()
NAME = os.getenv("C42B_TEST_DATABASE_NAME", "").strip()


@unittest.skipUnless(URL and NAME, "configure C42B_TEST_DATABASE_URL e C42B_TEST_DATABASE_NAME")
class TestC42BPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(URL)
        if parsed.get_backend_name() != "postgresql" or parsed.database != NAME or not NAME.startswith("quizhub_c42b_test_"):
            raise RuntimeError("C4.2B exige PostgreSQL descartável quizhub_c42b_test_*")
        cls.engine = create_engine(URL, pool_size=8, max_overflow=2, pool_pre_ping=True)

    @classmethod
    def tearDownClass(cls): cls.engine.dispose()

    def criar(self):
        marca = uuid4().hex[:10]
        with Session(self.engine, expire_on_commit=False) as db:
            admin1 = Usuario(nome="A1", email=f"a1-{marca}@test", senha_hash="x", perfil="ADMIN")
            admin2 = Usuario(nome="A2", email=f"a2-{marca}@test", senha_hash="x", perfil="ADMIN")
            cat = Categoria(slug=f"macabro-{marca}", nome="Macabro", modo="NEM_A_PATO", origem="OFICIAL")
            catalogo = CatalogoOficial(catalogo_id=f"np-{marca}", versao=1, modo="NEM_A_PATO", status="PREPARADO", sha256=marca.ljust(64, "a"))
            db.add_all([admin1, admin2, cat, catalogo]); db.flush()
            r = CatalogoOficialRascunho(catalogo_origem_id=catalogo.id, catalogo_id=catalogo.catalogo_id, modo="NEM_A_PATO", versao_base=1, numero_rascunho=1, nome="Concorrência", criado_por_id=admin1.id, modificado_por_id=admin1.id)
            db.add(r); db.flush()
            for i in range(100):
                p = PerguntaNemPatoRascunho(rascunho_id=r.id, id_editorial=f"{marca}-{i:03}", categoria_id=cat.id, categoria_slug_snapshot=cat.slug, categoria_nome_snapshot=cat.nome, ordem=i+1, enunciado=f"Pergunta {i}?", resposta_numerica=i, unidade="itens", explicacao="Explicação factual extensa e documental para homologação concorrente.", tema_editorial="História", natureza_resposta="EXATA", ativa=True, tipo_alteracao="INALTERADA", revisao=1, modificado_por_id=admin1.id)
                p.fontes = [FontePerguntaNemPatoRascunho(ordem=1, titulo="Fonte", url=f"https://example.test/{marca}/{i}", acessada_em=date(2026,1,1))]
                db.add(p)
            db.commit(); return r.id, admin1.id, admin2.id

    @staticmethod
    def relatorio(rid):
        return {"rascunho_id": rid, "revisao_validada": 1, "resumo": {"perguntas_examinadas":100,"perguntas_publicaveis":100,"perguntas_validas_estruturalmente":100,"perguntas_com_problemas":0,"erros":0,"avisos":0,"informacoes":0}, "achados":[]}

    def test_duas_decisoes_simultaneas(self):
        rid, a1, a2 = self.criar()
        with Session(self.engine) as db, patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio(rid)):
            _, ciclo = encaminhar_revisao(db, rid, 1, db.get(Usuario,a1)); db.commit()
            item = db.scalar(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id==ciclo.id)); pid=item.pergunta_nem_pato_id
        barreira=Barrier(2)
        def executar(aid, decisao):
            try:
                with Session(self.engine) as db:
                    barreira.wait(timeout=5)
                    decidir_pergunta(db,rid,pid,1,1,{"decisao":decisao,"justificativa":"Decisão concorrente documentalmente justificada.","relacao_fontes_resposta":None},db.get(Usuario,aid)); db.commit(); return 200
            except HTTPException as e: return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados=list(pool.map(lambda x: executar(*x),[(a1,"APROVADA"),(a2,"REPROVADA")]))
        self.assertEqual(sorted(resultados),[200,412])
        with Session(self.engine) as db:
            item=db.scalar(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id==ciclo.id,ItemRevisaoPergunta.pergunta_nem_pato_id==pid)); self.assertEqual(item.revisao_editorial,2)

    def test_encaminhamentos_concorrentes_criam_um_ciclo(self):
        rid,a1,a2=self.criar(); barreira=Barrier(2)
        def executar(aid):
            try:
                with Session(self.engine) as db, patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio(rid)):
                    barreira.wait(timeout=5); encaminhar_revisao(db,rid,1,db.get(Usuario,aid)); db.commit(); return 200
            except HTTPException as e: return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool: resultados=list(pool.map(executar,[a1,a2]))
        self.assertEqual(sorted(resultados),[200,409])
        with Session(self.engine) as db:
            ciclos=list(db.scalars(select(CicloRevisaoRascunho).where(CicloRevisaoRascunho.rascunho_id==rid))); self.assertEqual(len(ciclos),1); self.assertEqual(ciclos[0].estado,"EM_ANDAMENTO")

    def test_reabertura_concorrente_invalida_uma_vez(self):
        rid,a1,a2=self.criar()
        with Session(self.engine) as db:
            r=db.get(CatalogoOficialRascunho,rid); r.status="APROVADO"
            c=CicloRevisaoRascunho(rascunho_id=rid,revisao_conteudo=1,revisao_editorial=1,hash_validacao="f"*64,versao_regras="C4.1-v1",total_erros=0,total_avisos=0,total_informacoes=0,estado="CONCLUIDO",responsavel_id=a1); db.add(c); db.flush()
            db.add(AprovacaoRascunho(rascunho_id=rid,ciclo_id=c.id,revisao_conteudo=1,hash_validacao=c.hash_validacao,responsavel_id=a1,confirmacao_explicita=True,autorrevisao=False,valida=True)); db.commit()
        barreira=Barrier(2)
        def executar(aid):
            try:
                with Session(self.engine) as db:
                    barreira.wait(timeout=5); reabrir(db,rid,1,"Reabertura concorrente devidamente justificada.",db.get(Usuario,aid)); db.commit(); return 200
            except HTTPException as e: return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool: resultados=list(pool.map(executar,[a1,a2]))
        self.assertEqual(sorted(resultados),[200,409])
        with Session(self.engine) as db:
            a=db.scalar(select(AprovacaoRascunho).where(AprovacaoRascunho.rascunho_id==rid)); self.assertFalse(a.valida); self.assertIsNotNone(a.invalidada_em)

    def test_fluxo_completo_cem_perguntas_bigint_e_novo_ciclo(self):
        rid,a1,_=self.criar()
        with Session(self.engine, expire_on_commit=False) as db, patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio(rid)):
            tabelas_definitivas=(Pergunta,PerguntaNemPato,FontePerguntaOficial,FontePerguntaNemPatoOficial,Partida,Temporada)
            antes=tuple(db.scalar(select(func.count()).select_from(modelo)) for modelo in tabelas_definitivas)
            maior=db.scalar(select(PerguntaNemPatoRascunho).where(PerguntaNemPatoRascunho.rascunho_id==rid).order_by(PerguntaNemPatoRascunho.ordem).limit(1)); maior.resposta_numerica=2**63-1; db.commit()
            admin=db.get(Usuario,a1); r,c=encaminhar_revisao(db,rid,1,admin); db.commit()
            itens=list(db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id==c.id)))
            for item in itens:
                fonte=db.scalar(select(FontePerguntaNemPatoRascunho).where(FontePerguntaNemPatoRascunho.pergunta_rascunho_id==item.pergunta_nem_pato_id))
                item,c=verificar_fonte(db,rid,item.pergunta_nem_pato_id,fonte.id,1,item.revisao_editorial,{"resultado":"SUFICIENTE","evidencia_documental":"Documento consultado diretamente e número confirmado.","relacao_com_resposta":"A referência sustenta explicitamente a resposta.","justificativa":None},admin)
                item,c=decidir_pergunta(db,rid,item.pergunta_nem_pato_id,1,item.revisao_editorial,{"decisao":"APROVADA","justificativa":"Resposta e explicação conferidas documentalmente.","relacao_fontes_resposta":"Relação direta."},admin)
            r,c,a=aprovar(db,rid,1,c.revisao_editorial,{"confirmacao_explicita":True,"justificativa_autorrevisao":"Autorrevisão controlada com evidências individuais e equipe reduzida."},admin); db.commit()
            self.assertEqual(r.status,"APROVADO"); self.assertTrue(a.valida); self.assertEqual(db.get(PerguntaNemPatoRascunho,maior.id).resposta_numerica,2**63-1)
            r,c=reabrir(db,rid,1,"Nova evidência exige revisão editorial adicional.",admin); db.commit(); self.assertEqual(r.status,"EM_EDICAO"); self.assertFalse(a.valida)
            r,novo=encaminhar_revisao(db,rid,1,admin); db.commit(); self.assertNotEqual(novo.id,c.id); self.assertEqual(novo.estado,"EM_ANDAMENTO")
            depois=tuple(db.scalar(select(func.count()).select_from(modelo)) for modelo in tabelas_definitivas); self.assertEqual(antes,depois)

    def test_aprovacao_concorrente_com_decisao(self):
        rid,a1,a2=self.criar()
        with Session(self.engine) as db, patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio(rid)):
            _,c=encaminhar_revisao(db,rid,1,db.get(Usuario,a1)); db.commit()
            itens=list(db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id==c.id)))
            for item in itens:
                item.estado="APROVADA"; item.revisor_id=a1
                fonte=db.scalar(select(FontePerguntaNemPatoRascunho).where(FontePerguntaNemPatoRascunho.pergunta_rascunho_id==item.pergunta_nem_pato_id))
                db.add(VerificacaoFonteRevisao(item_id=item.id,fonte_nem_pato_id=fonte.id,fonte_titulo=fonte.titulo,fonte_url=fonte.url,fonte_acessada_em=str(fonte.acessada_em),fingerprint="b"*64,resultado="SUFICIENTE",evidencia_documental="Evidência documental suficiente.",relacao_com_resposta="Relação direta.",responsavel_id=a1))
            alvo=itens[0].pergunta_nem_pato_id; db.commit()
        barreira=Barrier(2)
        def decisao():
            try:
                with Session(self.engine) as db:
                    barreira.wait(timeout=5); decidir_pergunta(db,rid,alvo,1,1,{"decisao":"REPROVADA","justificativa":"Nova análise documental reprovou a pergunta.","relacao_fontes_resposta":None},db.get(Usuario,a2)); db.commit(); return ("decisao",200)
            except HTTPException as e:return ("decisao",e.status_code)
        def aprovacao():
            try:
                with Session(self.engine) as db, patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio(rid)):
                    barreira.wait(timeout=5); aprovar(db,rid,1,1,{"confirmacao_explicita":True,"justificativa_autorrevisao":None},db.get(Usuario,a2)); db.commit(); return ("aprovacao",200)
            except HTTPException as e:return ("aprovacao",e.status_code)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros=[pool.submit(decisao),pool.submit(aprovacao)]; resultados=[f.result(timeout=10) for f in futuros]
        self.assertIn(resultados, [[("decisao",200),("aprovacao",412)],[("decisao",409),("aprovacao",200)]])

    def test_devolucao_concorrente_com_revisao(self):
        rid,a1,a2=self.criar()
        with Session(self.engine) as db, patch("app.services.revisao_editorial_rascunhos.validar_rascunho_oficial", return_value=self.relatorio(rid)):
            _,c=encaminhar_revisao(db,rid,1,db.get(Usuario,a1)); db.commit(); alvo=db.scalar(select(ItemRevisaoPergunta.pergunta_nem_pato_id).where(ItemRevisaoPergunta.ciclo_id==c.id))
        barreira=Barrier(2)
        def executar(tipo):
            try:
                with Session(self.engine) as db:
                    barreira.wait(timeout=5)
                    if tipo=="decisao": decidir_pergunta(db,rid,alvo,1,1,{"decisao":"APROVADA","justificativa":"Decisão factual concorrente devidamente justificada.","relacao_fontes_resposta":None},db.get(Usuario,a1))
                    else: devolver_edicao(db,rid,1,"Devolução concorrente devidamente justificada.",db.get(Usuario,a2),revisao_editorial=1)
                    db.commit(); return (tipo,200)
            except HTTPException as e:return (tipo,e.status_code)
        with ThreadPoolExecutor(max_workers=2) as pool: resultados=list(pool.map(executar,["decisao","devolucao"]))
        self.assertIn(resultados, [[("decisao",200),("devolucao",412)],[("decisao",409),("devolucao",200)]])


if __name__ == "__main__": unittest.main()
