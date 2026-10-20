import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Categoria, OperacaoAdministrativa, Usuario
from app.services.idempotencia_administrativa import (
    executar_operacao_idempotente,
    hash_requisicao_canonica,
    marcar_operacoes_interrompidas,
)


class TestIdempotenciaAdministrativa(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.admin_a = uuid4()
        self.admin_b = uuid4()
        self.jogador = uuid4()
        with self.factory.begin() as db:
            db.add_all([
                Usuario(
                    id=self.admin_a, nome="Admin A", email="a@admin.test",
                    senha_hash="hash", perfil="ADMIN",
                ),
                Usuario(
                    id=self.admin_b, nome="Admin B", email="b@admin.test",
                    senha_hash="hash", perfil="ADMIN",
                ),
                Usuario(
                    id=self.jogador, nome="Jogador", email="jogador@admin.test",
                    senha_hash="hash", perfil="JOGADOR",
                ),
            ])

    def tearDown(self):
        self.engine.dispose()

    def _executar(self, admin, chave, pedido, callback, **kwargs):
        return executar_operacao_idempotente(
            self.factory,
            administrador_id=admin,
            tipo_operacao="PUBLICAR_CATALOGO",
            recurso_tipo="CATALOGO_OFICIAL",
            recurso_id="quiz-v3",
            chave_idempotencia=chave,
            pedido=pedido,
            executar=callback,
            **kwargs,
        )

    def test_primeira_execucao_e_repeticao_devolvem_resultado_persistido(self):
        chamadas = 0

        def callback(db):
            nonlocal chamadas
            chamadas += 1
            return 201, {"catalogo": "quiz-v3", "token": "segredo"}

        primeira = self._executar(self.admin_a, "chave-1", {"versao": 3}, callback)
        repetida = self._executar(self.admin_a, "chave-1", {"versao": 3}, callback)
        self.assertFalse(primeira.reproduzido)
        self.assertTrue(repetida.reproduzido)
        self.assertEqual((primeira.codigo, repetida.codigo), (201, 201))
        self.assertEqual(chamadas, 1)
        self.assertEqual(repetida.resposta["token"], "[REMOVIDO]")

    def test_mesma_chave_pedido_diferente_e_chave_ausente(self):
        self._executar(self.admin_a, "chave-2", {"versao": 3}, lambda db: (200, {}))
        with self.assertRaises(HTTPException) as conflito:
            self._executar(
                self.admin_a, "chave-2", {"versao": 4}, lambda db: (200, {})
            )
        self.assertEqual(conflito.exception.status_code, 409)
        self.assertEqual(
            conflito.exception.detail["codigo"],
            "CHAVE_IDEMPOTENCIA_REUTILIZADA",
        )
        with self.assertRaises(HTTPException) as ausente:
            self._executar(self.admin_a, None, {}, lambda db: (200, {}))
        self.assertEqual(ausente.exception.status_code, 428)

    def test_falha_reverte_negocio_e_exige_recuperacao_explicita(self):
        def falhar(db):
            db.add(Categoria(
                slug="nao-persistir", nome="Não persistir",
                modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=True,
            ))
            db.flush()
            raise RuntimeError("segredo que não deve ser persistido")

        with self.assertRaises(RuntimeError):
            self._executar(self.admin_a, "chave-falha", {"versao": 3}, falhar)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count(Categoria.id))), 0)
            operacao = db.scalar(select(OperacaoAdministrativa))
            self.assertEqual(operacao.estado, "FALHOU")
            self.assertNotIn("segredo", str(operacao.resposta_sanitizada))

        with self.assertRaises(HTTPException) as bloqueada:
            self._executar(
                self.admin_a, "chave-falha", {"versao": 3},
                lambda db: (200, {}),
            )
        self.assertEqual(bloqueada.exception.status_code, 409)

        recuperada = self._executar(
            self.admin_a, "chave-falha", {"versao": 3},
            lambda db: (200, {"ok": True}), permitir_recuperacao=True,
        )
        self.assertFalse(recuperada.reproduzido)
        with self.factory() as db:
            operacao = db.scalar(select(OperacaoAdministrativa))
            self.assertEqual((operacao.estado, operacao.tentativas), ("CONCLUIDA", 2))

    def test_separacao_entre_administradores(self):
        primeiro = self._executar(
            self.admin_a, "mesma-chave", {"versao": 3}, lambda db: (200, {})
        )
        segundo = self._executar(
            self.admin_b, "mesma-chave", {"versao": 3}, lambda db: (200, {})
        )
        self.assertNotEqual(primeiro.operacao_id, segundo.operacao_id)

    def test_jogador_nao_reserva_operacao_administrativa(self):
        with self.assertRaises(HTTPException) as negada:
            self._executar(
                self.jogador, "sem-permissao", {"versao": 3},
                lambda db: (200, {}),
            )
        self.assertEqual(negada.exception.status_code, 403)

    def test_commit_concluido_antes_da_resposta_e_recuperado_sem_reexecutar(self):
        chamadas = 0

        def callback(db):
            nonlocal chamadas
            chamadas += 1
            return 202, {"estado": "aceita"}

        # A primeira chamada persiste efeitos e resposta. Uma perda de conexão
        # depois desse commit é representada pela ausência de uso do retorno.
        self._executar(self.admin_a, "resposta-perdida", {"versao": 3}, callback)
        recuperada = self._executar(
            self.admin_a, "resposta-perdida", {"versao": 3}, callback
        )
        self.assertEqual(chamadas, 1)
        self.assertTrue(recuperada.reproduzido)
        self.assertEqual((recuperada.codigo, recuperada.resposta), (
            202, {"estado": "aceita"}
        ))

    def test_operacao_interrompida_e_identificavel_e_recuperavel(self):
        antiga = datetime.now(timezone.utc) - timedelta(hours=2)
        with self.factory.begin() as db:
            db.add(OperacaoAdministrativa(
                administrador_id=self.admin_a,
                tipo_operacao="PUBLICAR_CATALOGO",
                recurso_tipo="CATALOGO_OFICIAL",
                recurso_id="quiz-v3",
                chave_idempotencia="interrompida",
                hash_requisicao=hash_requisicao_canonica(
                    {"versao": 3},
                    recurso_tipo="CATALOGO_OFICIAL", recurso_id="quiz-v3",
                ),
                atualizada_em=antiga,
            ))
        with self.factory.begin() as db:
            self.assertEqual(
                marcar_operacoes_interrompidas(
                    db, anteriores_a=datetime.now(timezone.utc) - timedelta(hours=1)
                ),
                1,
            )
        resultado = self._executar(
            self.admin_a, "interrompida", {"versao": 3},
            lambda db: (200, {"recuperada": True}),
            permitir_recuperacao=True,
        )
        self.assertEqual(resultado.resposta, {"recuperada": True})


if __name__ == "__main__":
    unittest.main()
