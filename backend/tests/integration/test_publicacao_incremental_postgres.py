import hashlib
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import (AprovacaoRascunho, CatalogoOficial, CatalogoOficialRascunho,
    Categoria, CicloRevisaoRascunho, FontePerguntaNemPatoRascunho, Jogador,
    ItemRevisaoPergunta, Partida, PartidaPergunta, Pergunta, PerguntaNemPato,
    PerguntaNemPatoRascunho, Temporada, Usuario)
from app.security import JWT_COOKIE_NAME, criar_token_acesso, password_hash
from app.services.publicacao_incremental_catalogos import publicar_rascunho
from app.services.rascunhos_catalogos_oficiais import criar_rascunho, salvar_pergunta
from app.services.revisao_editorial_rascunhos import encaminhar_revisao
from app.services.ranking import ranking_service
from app.services.validacao_rascunhos_oficiais import validar_rascunho_oficial

URL=os.getenv("PUBLICACAO_INCREMENTAL_TEST_DATABASE_URL","").strip()
NAME=os.getenv("PUBLICACAO_INCREMENTAL_TEST_DATABASE_NAME","").strip()


@unittest.skipUnless(URL and NAME,"configure banco descartável de publicação incremental")
class TestPublicacaoIncrementalPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=make_url(URL)
        if url.get_backend_name()!="postgresql" or url.database!=NAME or not NAME.startswith("quizhub_incremental_test_") or url.port==5432:
            raise RuntimeError("exige PostgreSQL descartável fora da porta 5432")
        cls.engine=create_engine(URL,pool_size=8,max_overflow=4,pool_pre_ping=True)
        cls.factory=sessionmaker(cls.engine,expire_on_commit=False)
        cls.env=patch.dict(os.environ,{"JWT_SECRET":"incremental-test-secret-with-32-bytes"}); cls.env.start()

    @classmethod
    def tearDownClass(cls): cls.env.stop(); cls.engine.dispose()

    def criar_base(self, quantidade=15):
        marca=uuid4().hex[:10]
        with self.factory.begin() as db:
            db.execute(update(CatalogoOficial).where(CatalogoOficial.modo=="NEM_A_PATO",CatalogoOficial.status=="ATIVO").values(status="ARQUIVADO",arquivado_em=datetime.now(timezone.utc)))
            admin=Usuario(nome="Admin",email=f"admin-{marca}@test",senha_hash=password_hash.hash("senha"),perfil="ADMIN")
            jogador=Usuario(nome="Jogador",email=f"jogador-{marca}@test",senha_hash=password_hash.hash("senha"),perfil="JOGADOR")
            cat=Categoria(slug=f"macabro-{marca}",nome="Macabro",modo="NEM_A_PATO",origem="OFICIAL")
            base=CatalogoOficial(catalogo_id=f"np-{marca}",versao=1,modo="NEM_A_PATO",status="ATIVO",sha256="0"*64)
            db.add_all([admin,jogador,cat,base]); db.flush()
            rid=self._rascunho_aprovado(db,base,admin,cat,quantidade,marca)
            return rid,admin.id,jogador.id,base.id,cat.id

    def _rascunho_aprovado(self,db,base,admin,cat,quantidade,marca,numero=1):
        r=CatalogoOficialRascunho(catalogo_origem_id=base.id,catalogo_id=base.catalogo_id,modo="NEM_A_PATO",versao_base=base.versao,numero_rascunho=numero,nome=f"Lote {numero}",status="APROVADO",criado_por_id=admin.id,modificado_por_id=admin.id)
        db.add(r); db.flush()
        for i in range(quantidade):
            p=PerguntaNemPatoRascunho(rascunho_id=r.id,id_editorial=f"{marca}-{i:03}",categoria_id=cat.id,categoria_slug_snapshot=cat.slug,categoria_nome_snapshot=cat.nome,ordem=i+1,enunciado=f"Quantos itens há no registro {i}?",resposta_numerica=i,unidade="itens",explicacao="Explicação documental suficientemente detalhada para validação.",tema_editorial="História",natureza_resposta="EXATA",ativa=True,tipo_alteracao="ADICIONADA",revisao=1,modificado_por_id=admin.id)
            p.fontes=[FontePerguntaNemPatoRascunho(ordem=1,titulo="Fonte institucional",url=f"https://example.test/{marca}/{i}",acessada_em=date(2026,1,1))]; db.add(p)
        db.flush(); rel=validar_rascunho_oficial(db,r.id); h=hashlib.sha256(json.dumps(rel,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
        c=CicloRevisaoRascunho(rascunho_id=r.id,revisao_conteudo=1,revisao_editorial=1,hash_validacao=h,versao_regras="teste",total_erros=0,total_avisos=rel["resumo"]["avisos"],total_informacoes=rel["resumo"]["informacoes"],estado="CONCLUIDO",responsavel_id=admin.id)
        db.add(c); db.flush(); db.add(AprovacaoRascunho(rascunho_id=r.id,ciclo_id=c.id,revisao_conteudo=1,hash_validacao=h,responsavel_id=admin.id,confirmacao_explicita=True,autorrevisao=False,valida=True)); db.flush(); return r.id

    def test_publicacoes_concorrentes_apenas_uma_vence(self):
        rid1,aid,_,baseid,catid=self.criar_base()
        with self.factory.begin() as db:
            base=db.get(CatalogoOficial,baseid); admin=db.get(Usuario,aid); cat=db.get(Categoria,catid)
            rid2=self._rascunho_aprovado(db,base,admin,cat,15,uuid4().hex[:10],numero=2)
        barreira=Barrier(2)
        def executar(rid):
            try:
                with self.factory() as db:
                    barreira.wait(timeout=5); publicar_rascunho(db,rid,1,db.get(Usuario,aid),"Publicação concorrente devidamente autorizada."); db.commit(); return 201
            except HTTPException as exc: return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool: resultados=list(pool.map(executar,[rid1,rid2]))
        self.assertEqual(sorted(resultados),[201,409])
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CatalogoOficial).where(CatalogoOficial.modo=="NEM_A_PATO",CatalogoOficial.status=="ATIVO",CatalogoOficial.catalogo_id==db.get(CatalogoOficial,baseid).catalogo_id)),1)

    def test_falha_antes_da_ativacao_reverte_tudo(self):
        rid,aid,_,baseid,_=self.criar_base()
        with self.assertRaisesRegex(RuntimeError,"falha injetada"):
            with self.factory() as db, patch("app.services.publicacao_incremental_catalogos._antes_de_ativar",side_effect=RuntimeError("falha injetada")):
                publicar_rascunho(db,rid,1,db.get(Usuario,aid),"Teste transacional com falha injetada."); db.commit()
        with self.factory() as db:
            self.assertEqual(db.get(CatalogoOficial,baseid).status,"ATIVO"); self.assertEqual(db.get(CatalogoOficialRascunho,rid).status,"APROVADO")
            self.assertEqual(db.scalar(select(func.count()).select_from(CatalogoOficial).where(CatalogoOficial.catalogo_id==db.get(CatalogoOficial,baseid).catalogo_id)),1)

    def test_http_idempotencia_seguranca_e_conflito(self):
        rid,aid,jid,_,_=self.criar_base(); factory_patch=patch("app.api.v1.admin.get_session_factory",return_value=self.factory); factory_patch.start()
        def banco():
            with self.factory() as db: yield db
        app.dependency_overrides[get_db]=banco
        try:
            with TestClient(app) as client:
                rota=f"/api/v1/admin/catalogos/rascunhos/{rid}/publicar"; payload={"justificativa":"Publicação incremental homologada documentalmente."}
                self.assertEqual(client.post(rota,json=payload,headers={"Origin":"http://testserver","Idempotency-Key":"pub-http","If-Match":"1"}).status_code,401)
                client.cookies.set(JWT_COOKIE_NAME,criar_token_acesso(jid,agora=datetime.now(timezone.utc))); self.assertEqual(client.post(rota,json=payload,headers={"Origin":"http://testserver","Idempotency-Key":"pub-http","If-Match":"1"}).status_code,403)
                client.cookies.clear(); client.cookies.set(JWT_COOKIE_NAME,criar_token_acesso(aid,agora=datetime.now(timezone.utc)))
                self.assertEqual(client.post(rota,json=payload,headers={"Origin":"http://testserver","X-CSRF-Token":"invalido","Idempotency-Key":"pub-http","If-Match":"1"}).status_code,403)
                csrf=client.get("/api/v1/admin/csrf").json()["token"]; headers={"Origin":"http://testserver","X-CSRF-Token":csrf,"Idempotency-Key":"pub-http","If-Match":"1"}
                primeira=client.post(rota,json=payload,headers=headers); self.assertEqual(primeira.status_code,200,primeira.text)
                repetida=client.post(rota,json=payload,headers=headers); self.assertEqual(repetida.json(),primeira.json())
                conflito=client.post(rota,json={"justificativa":"Outra justificativa documental válida."},headers=headers); self.assertEqual(conflito.status_code,409)
                with self.factory() as db: self.assertEqual(db.scalar(select(func.count()).select_from(CatalogoOficial).where(CatalogoOficial.catalogo_id==primeira.json()["catalogo_id"])),2)
        finally: app.dependency_overrides.clear(); factory_patch.stop()

    def test_clonagem_ativa_preserva_fontes_e_modificacao_exige_revisao(self):
        rid,aid,_,_,_=self.criar_base()
        with self.factory.begin() as db: _,publicado,_=publicar_rascunho(db,rid,1,db.get(Usuario,aid),"Publicação base para testar clonagem ativa.")
        with self.factory.begin() as db:
            novo=criar_rascunho(db,publicado.id,"Incremento seguinte",db.get(Usuario,aid)); novo_id=novo.id
        with self.factory() as db:
            itens=list(db.scalars(select(PerguntaNemPatoRascunho).where(PerguntaNemPatoRascunho.rascunho_id==novo_id).order_by(PerguntaNemPatoRascunho.ordem)))
            self.assertEqual(len(itens),15); self.assertTrue(all(p.tipo_alteracao=="INALTERADA" and len(p.fontes)==1 for p in itens))
        with self.factory.begin() as db:
            item=db.scalar(select(PerguntaNemPatoRascunho).where(PerguntaNemPatoRascunho.rascunho_id==novo_id).order_by(PerguntaNemPatoRascunho.ordem))
            payload={"id_editorial":item.id_editorial,"categoria_id":item.categoria_id,"enunciado":item.enunciado+" Revisada", "explicacao":item.explicacao,"ativa":True,"resposta_numerica":str(item.resposta_numerica),"unidade":item.unidade,"fonte":item.fonte,"fonte_url":item.fonte_url,"fonte_acessada_em":item.fonte_acessada_em,"tema_editorial":item.tema_editorial,"natureza_resposta":item.natureza_resposta,"qualificacao_estimativa":item.qualificacao_estimativa,"referencias":[{"titulo":f.titulo,"url":f.url,"acessada_em":f.acessada_em} for f in item.fontes]}
            salvar_pergunta(db,novo_id,item.id,payload,db.get(Usuario,aid),1)
            _,ciclo=encaminhar_revisao(db,novo_id,2,db.get(Usuario,aid))
            revisadas=list(db.scalars(select(ItemRevisaoPergunta).where(ItemRevisaoPergunta.ciclo_id==ciclo.id)))
            self.assertEqual([(x.pergunta_nem_pato_id,x.id_editorial) for x in revisadas],[(item.id,item.id_editorial)])

    def test_partida_snapshot_e_ranking_permanecem_integros(self):
        rid,aid,_,_,_=self.criar_base(); marca=uuid4().hex[:8]
        with self.factory.begin() as db:
            db.execute(update(CatalogoOficial).where(CatalogoOficial.modo=="QUIZ_CLASSICO",CatalogoOficial.status=="ATIVO").values(status="ARQUIVADO",arquivado_em=datetime.now(timezone.utc)))
            db.execute(update(Temporada).where(Temporada.status=="ATIVA").values(status="ENCERRADA",encerra_em=datetime.now(timezone.utc)))
            cat=Categoria(slug=f"geral-{marca}",nome="Geral",modo="QUIZ_CLASSICO",origem="OFICIAL")
            catalogo=CatalogoOficial(catalogo_id=f"quiz-{marca}",versao=1,modo="QUIZ_CLASSICO",status="ATIVO",sha256="1"*64)
            temporada=Temporada(numero=(db.scalar(select(func.max(Temporada.numero))) or 0)+1,nome=f"Temporada {marca}",status="ATIVA",inicia_em=datetime.now(timezone.utc))
            jogador=Jogador(nome="Histórico")
            db.add_all([cat,catalogo,temporada,jogador]); db.flush()
            pid=(db.scalar(select(func.max(Pergunta.id))) or 0)+1
            pergunta=Pergunta(id=pid,categoria_id=cat.id,enunciado="Pergunta histórica?",alternativa_a="A",alternativa_b="B",alternativa_c="C",alternativa_d="D",alternativa_correta=0,explicacao="Explicação histórica.",dificuldade="FACIL",origem="OFICIAL",catalogo_oficial_id=catalogo.id,id_editorial=f"HIST-{marca}")
            partida=Partida(jogador_id=jogador.id,categoria_id=cat.id,temporada_id=temporada.id,status="FINALIZADA",pontuacao=100,acertos=1,erros=0,finalizada_em=datetime.now(timezone.utc)); db.add_all([pergunta,partida]); db.flush()
            snapshot=PartidaPergunta(partida_id=partida.id,pergunta_id=pergunta.id,ordem=1,categoria_id_snapshot=cat.id,enunciado_snapshot=pergunta.enunciado,alternativa_a_snapshot="A",alternativa_b_snapshot="B",alternativa_c_snapshot="C",alternativa_d_snapshot="D",alternativa_correta_snapshot=0,explicacao_snapshot=pergunta.explicacao); db.add(snapshot); db.flush()
            partida_id,snapshot_id,temporada_id=partida.id,snapshot.id,temporada.id
        with self.factory.begin() as db: publicar_rascunho(db,rid,1,db.get(Usuario,aid),"Publicação sem impacto sobre histórico do Quiz Clássico.")
        with self.factory() as db:
            partida=db.get(Partida,partida_id); snapshot=db.get(PartidaPergunta,snapshot_id); ranking=ranking_service.listar(db,temporada=temporada_id,limit=10)
            self.assertEqual((partida.pontuacao,snapshot.enunciado_snapshot),(100,"Pergunta histórica?")); self.assertEqual([(x.jogador,x.pontuacao) for x in ranking],[('Histórico',100)])
