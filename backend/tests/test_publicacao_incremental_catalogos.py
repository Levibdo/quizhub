import unittest
import hashlib
import json
from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (AprovacaoRascunho, CatalogoOficial, CatalogoOficialRascunho,
    Categoria, CicloRevisaoRascunho, FontePerguntaNemPatoRascunho,
    PerguntaNemPato, PerguntaNemPatoRascunho, Usuario)
from app.services.publicacao_incremental_catalogos import publicar_rascunho
from app.services.validacao_rascunhos_oficiais import validar_rascunho_oficial


class TestPublicacaoIncremental(unittest.TestCase):
    def setUp(self):
        # Este módulo exercita o serviço de forma unitária. A integração
        # PostgreSQL tem uma suíte dedicada e não deve compartilhar seu banco
        # nem seus identificadores fixos com estes casos.
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = Usuario(nome="Admin", email="incremental@example.test", senha_hash="hash", perfil="ADMIN")
        self.categoria = Categoria(slug="macabro-inc", nome="Macabro incremental", modo="NEM_A_PATO", origem="OFICIAL")
        self.base = CatalogoOficial(catalogo_id="np_incremental", versao=1, modo="NEM_A_PATO", status="ATIVO", sha256="0" * 64)
        self.db.add_all([self.admin, self.categoria, self.base]); self.db.flush()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def rascunho(self, origem, numero, inicio, fim):
        r = CatalogoOficialRascunho(catalogo_origem_id=origem.id, catalogo_id=origem.catalogo_id, modo="NEM_A_PATO", versao_base=origem.versao, numero_rascunho=numero, nome=f"Lote {numero}", status="APROVADO", criado_por_id=self.admin.id, modificado_por_id=self.admin.id)
        self.db.add(r); self.db.flush()
        if numero == 2:
            anteriores = list(self.db.scalars(select(PerguntaNemPato).where(PerguntaNemPato.catalogo_oficial_id == origem.id).order_by(PerguntaNemPato.id_editorial)))
            for ordem, p in enumerate(anteriores, 1): self._pergunta(r, ordem, int(p.id_editorial.split("-")[-1]), "INALTERADA")
        for valor in range(inicio, fim): self._pergunta(r, valor + 1, valor, "ADICIONADA")
        self.db.flush(); relatorio=validar_rascunho_oficial(self.db,r.id); resumo=relatorio["resumo"]
        hash_validacao=hashlib.sha256(json.dumps(relatorio,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
        ciclo = CicloRevisaoRascunho(rascunho_id=r.id, revisao_conteudo=1, revisao_editorial=1, hash_validacao=hash_validacao, versao_regras="teste", total_erros=resumo["erros"], total_avisos=resumo["avisos"], total_informacoes=resumo["informacoes"], estado="CONCLUIDO", responsavel_id=self.admin.id)
        self.db.add(ciclo); self.db.flush(); self.db.add(AprovacaoRascunho(rascunho_id=r.id, ciclo_id=ciclo.id, revisao_conteudo=1, hash_validacao=hash_validacao, responsavel_id=self.admin.id, confirmacao_explicita=True, autorrevisao=False, valida=True)); self.db.flush(); return r

    def _pergunta(self, r, ordem, valor, tipo):
        p = PerguntaNemPatoRascunho(rascunho_id=r.id, id_editorial=f"INC-{valor:03}", categoria_id=self.categoria.id, categoria_slug_snapshot=self.categoria.slug, categoria_nome_snapshot=self.categoria.nome, ordem=ordem, enunciado=f"Quantos itens existem no caso documental {valor}?", resposta_numerica=valor, unidade="itens", explicacao="Explicação documental suficientemente detalhada para sustentar a resposta.", tema_editorial="História", natureza_resposta="EXATA", ativa=True, tipo_alteracao=tipo, revisao=1, modificado_por_id=self.admin.id)
        p.fontes=[FontePerguntaNemPatoRascunho(ordem=1,titulo="Fonte institucional",url=f"https://example.test/{valor}",acessada_em=date(2026,1,1))]; self.db.add(p)

    def test_publica_quinze_e_depois_trinta_sem_duplicar(self):
        r1=self.rascunho(self.base,1,0,15); _,v2,total=publicar_rascunho(self.db,r1.id,1,self.admin,"Publicação incremental inicial revisada."); self.db.commit()
        self.assertEqual(total,15)
        r2=self.rascunho(v2,2,15,30); _,v3,total=publicar_rascunho(self.db,r2.id,1,self.admin,"Publicação incremental complementar revisada."); self.db.commit()
        ids=list(self.db.scalars(select(PerguntaNemPato.id_editorial).where(PerguntaNemPato.catalogo_oficial_id==v3.id)))
        self.assertEqual((total,len(ids),len(set(ids))),(30,30,30)); self.assertEqual(v2.status,"ARQUIVADO"); self.assertEqual(v3.status,"ATIVO")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(PerguntaNemPato).where(PerguntaNemPato.catalogo_oficial_id==v2.id)),15)
