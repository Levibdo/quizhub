import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import (
    AuditoriaAdministrativa, CatalogoOficial, Categoria,
    FontePerguntaNemPatoOficial, PerguntaNemPato, Usuario,
)
from app.security import JWT_COOKIE_NAME, criar_token_acesso, password_hash
from app.services.reativacao_catalogos_oficiais import reativar_catalogo_oficial

URL = os.getenv("REATIVACAO_CATALOGOS_TEST_DATABASE_URL", "").strip()
NAME = os.getenv("REATIVACAO_CATALOGOS_TEST_DATABASE_NAME", "").strip()


@unittest.skipUnless(URL and NAME, "configure banco descartável de reativação")
class TestReativacaoCatalogosPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.get_backend_name() != "postgresql" or url.database != NAME or not NAME.startswith("quizhub_reativacao_test_") or url.port == 5432:
            raise RuntimeError("exige PostgreSQL descartável fora da porta 5432")
        cls.engine = create_engine(URL, pool_size=8, max_overflow=4, pool_pre_ping=True)
        cls.factory = sessionmaker(cls.engine, expire_on_commit=False)
        cls.env = patch.dict(os.environ, {"JWT_SECRET": "reativacao-test-secret-with-32-bytes"}); cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop(); cls.engine.dispose()

    def criar_cenario(self, quantidades=(15, 30)):
        marca = uuid4().hex[:10]
        with self.factory.begin() as db:
            db.execute(update(CatalogoOficial).where(CatalogoOficial.modo == "NEM_A_PATO", CatalogoOficial.status == "ATIVO").values(status="ARQUIVADO", arquivado_em=datetime.now(timezone.utc)))
            admin = Usuario(nome="Admin", email=f"admin-r-{marca}@test", senha_hash=password_hash.hash("senha"), perfil="ADMIN")
            jogador = Usuario(nome="Jogador", email=f"jog-r-{marca}@test", senha_hash=password_hash.hash("senha"), perfil="JOGADOR")
            categoria = Categoria(slug=f"macabro-r-{marca}", nome="Macabro", modo="NEM_A_PATO", origem="OFICIAL")
            db.add_all([admin, jogador, categoria]); db.flush()
            catalogos = []
            for versao, quantidade in enumerate(quantidades, 1):
                catalogo = CatalogoOficial(catalogo_id=f"np-r-{marca}", versao=versao, modo="NEM_A_PATO", status="ATIVO" if versao == len(quantidades) else "ARQUIVADO", sha256=str(versao) * 64)
                db.add(catalogo); db.flush(); catalogos.append(catalogo)
                for indice in range(quantidade):
                    pergunta = PerguntaNemPato(categoria_id=categoria.id, enunciado=f"Pergunta {versao}-{indice}?", resposta_numerica=indice, explicacao="Explicação documental", origem="OFICIAL", ativa=True, catalogo_oficial_id=catalogo.id, id_editorial=f"R-{versao}-{indice:03d}")
                    pergunta.fontes_editoriais = [FontePerguntaNemPatoOficial(ordem=1, titulo="Fonte", url=f"https://example.test/{marca}/{versao}/{indice}", acessada_em=date(2026, 10, 31))]
                    db.add(pergunta)
            db.flush()
            return admin.id, jogador.id, [item.id for item in catalogos]

    def test_alterna_15_e_30_sem_duplicar_ou_alterar_fontes(self):
        admin_id, _, (v15, v30) = self.criar_cenario()
        with self.factory.begin() as db:
            resposta = reativar_catalogo_oficial(db, v15, v30, db.get(Usuario, admin_id), "Retorno controlado à versão de quinze perguntas")
            self.assertEqual(resposta["perguntas_elegiveis"], 15)
        with self.factory() as db:
            self.assertEqual(db.get(CatalogoOficial, v15).status, "ATIVO")
            self.assertEqual(db.get(CatalogoOficial, v30).status, "ARQUIVADO")
            self.assertEqual(db.scalar(select(func.count(PerguntaNemPato.id)).where(PerguntaNemPato.catalogo_oficial_id == v15)), 15)
            self.assertEqual(db.scalar(select(func.count(PerguntaNemPato.id)).where(PerguntaNemPato.catalogo_oficial_id == v30)), 30)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuditoriaAdministrativa).where(AuditoriaAdministrativa.recurso_id == str(v15))), 1)

    def test_concorrencia_permite_uma_transicao(self):
        admin_id, _, ids = self.criar_cenario((15, 20, 30)); v15, v20, ativo = ids
        barreira = Barrier(2)
        def executar(alvo):
            try:
                with self.factory() as db:
                    barreira.wait(timeout=5)
                    reativar_catalogo_oficial(db, alvo, ativo, db.get(Usuario, admin_id), "Troca concorrente controlada e auditada")
                    db.commit(); return 200
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(executar, (v15, v20)))
        self.assertEqual(sorted(resultados), [200, 412])
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CatalogoOficial).where(CatalogoOficial.modo == "NEM_A_PATO", CatalogoOficial.status == "ATIVO")), 1)

    def test_falha_injetada_reverte_troca(self):
        admin_id, _, (v15, v30) = self.criar_cenario()
        with self.assertRaisesRegex(RuntimeError, "falha injetada"):
            with self.factory() as db, patch("app.services.reativacao_catalogos_oficiais._antes_de_reativar", side_effect=RuntimeError("falha injetada")):
                reativar_catalogo_oficial(db, v15, v30, db.get(Usuario, admin_id), "Teste de rollback transacional controlado")
                db.commit()
        with self.factory() as db:
            self.assertEqual(db.get(CatalogoOficial, v15).status, "ARQUIVADO")
            self.assertEqual(db.get(CatalogoOficial, v30).status, "ATIVO")

    def test_http_seguranca_idempotencia_e_conflito(self):
        admin_id, jogador_id, (v15, v30) = self.criar_cenario()
        factory_patch = patch("app.api.v1.admin.get_session_factory", return_value=self.factory); factory_patch.start()
        def banco():
            with self.factory() as db: yield db
        app.dependency_overrides[get_db] = banco
        try:
            with TestClient(app) as client:
                rota = f"/api/v1/admin/catalogos/{v15}/reativar"
                payload = {"justificativa": "Retorno controlado à versão anterior."}
                base = {"Origin": "http://testserver", "Idempotency-Key": "reativar-http", "If-Match": f'"{v30}"'}
                self.assertEqual(client.post(rota, json=payload, headers=base).status_code, 401)
                client.cookies.set(JWT_COOKIE_NAME, criar_token_acesso(jogador_id, agora=datetime.now(timezone.utc)))
                self.assertEqual(client.post(rota, json=payload, headers=base).status_code, 403)
                client.cookies.clear(); client.cookies.set(JWT_COOKIE_NAME, criar_token_acesso(admin_id, agora=datetime.now(timezone.utc)))
                self.assertEqual(client.post(rota, json=payload, headers=base | {"X-CSRF-Token": "invalido"}).status_code, 403)
                csrf = client.get("/api/v1/admin/csrf").json()["token"]
                self.assertEqual(client.post(rota, json={"justificativa": "curta"}, headers=base | {"X-CSRF-Token": csrf}).status_code, 422)
                self.assertEqual(client.post(rota, json=payload, headers=(base | {"If-Match": f'"{v15}"', "X-CSRF-Token": csrf, "Idempotency-Key": "reativar-stale"})).status_code, 412)
                versoes = client.get("/api/v1/admin/catalogos").json()["catalogos"]
                alvo_publico = next(item for item in versoes if item["id"] == str(v15))
                self.assertEqual((alvo_publico["elegivel_reativacao"], alvo_publico["quantidade_elegivel_reativacao"]), (True, 15))
                headers = base | {"X-CSRF-Token": csrf}
                primeira = client.post(rota, json=payload, headers=headers)
                self.assertEqual(primeira.status_code, 200, primeira.text)
                self.assertEqual(client.post(rota, json=payload, headers=headers).json(), primeira.json())
                conflito = client.post(rota, json={"justificativa": "Justificativa incompatível para a mesma chave."}, headers=headers)
                self.assertEqual(conflito.status_code, 409)
        finally:
            app.dependency_overrides.clear(); factory_patch.stop()
