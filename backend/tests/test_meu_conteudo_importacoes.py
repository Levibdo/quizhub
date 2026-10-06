import csv
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook
import jwt
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.conteudo import MODO_NEM_A_PATO, MODO_QUIZ_CLASSICO, ORIGEM_USUARIO
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Categoria, Pergunta, PerguntaNemPato, Usuario
from app.security import usuario_atual
from app.security import JWT_ALGORITHM, obter_segredo_jwt
from app.services.meu_conteudo_importacoes import (
    FINALIDADE_TOKEN,
    VERSAO_CONTRATO,
    meu_conteudo_importacoes_service,
)


CLASSIC = (
    "categoria_id", "enunciado", "alternativa_a", "alternativa_b",
    "alternativa_c", "alternativa_d", "alternativa_correta", "explicacao",
)
NP = (
    "categoria_id", "enunciado", "resposta_numerica", "explicacao",
    "unidade", "fonte",
)


def xlsx(cabecalho, linhas):
    workbook = Workbook()
    planilha = workbook.active
    planilha.append(cabecalho)
    for linha in linhas:
        planilha.append(linha)
    saida = BytesIO()
    workbook.save(saida)
    workbook.close()
    return saida.getvalue()


def csv_bytes(cabecalho, linhas):
    saida = StringIO(newline="")
    escritor = csv.writer(saida)
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return saida.getvalue().encode()


class TestMeuConteudoImportacoes(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            self.usuario = Usuario(
                nome="Ana", email=f"ana-{uuid4()}@example.com", senha_hash="hash"
            )
            self.outro = Usuario(
                nome="Bia", email=f"bia-{uuid4()}@example.com", senha_hash="hash"
            )
            db.add_all((self.usuario, self.outro))
            db.commit()
        self.classica = self.categoria("Classic", MODO_QUIZ_CLASSICO)
        self.np = self.categoria("NP", MODO_NEM_A_PATO)

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[usuario_atual] = lambda: self.usuario
        self.env = patch.dict(
            os.environ,
            {"JWT_SECRET": "segredo-c13b-testes-com-mais-de-32-bytes"},
        )
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def categoria(self, nome, modo, *, usuario=None, ativa=True, excluida=False):
        usuario = usuario or self.usuario
        categoria = Categoria(
            id=uuid4(), slug=f"c13b-{uuid4().hex[:8]}", nome=nome,
            modo=modo, origem=ORIGEM_USUARIO, usuario_id=usuario.id,
            ativa=False if excluida else ativa,
            excluida_em=datetime.now(timezone.utc) if excluida else None,
        )
        with self.sessions() as db:
            db.add(categoria)
            db.commit()
        return categoria

    def classic_dict(self, **mudancas):
        return {
            "categoria_id": str(self.classica.id), "enunciado": "Questão?",
            "alternativa_a": "A1", "alternativa_b": "B1",
            "alternativa_c": "C1", "alternativa_d": "D1",
            "alternativa_correta": "b", "explicacao": "Explicação",
            **mudancas,
        }

    def np_dict(self, **mudancas):
        return {
            "categoria_id": str(self.np.id), "enunciado": "Quantos?",
            "resposta_numerica": 42, "explicacao": "Explicação",
            "unidade": "itens", "fonte": "Fonte", **mudancas,
        }

    def conteudo(self, modo, formato, registros):
        campos = CLASSIC if modo == MODO_QUIZ_CLASSICO else NP
        if formato == "json":
            return json.dumps(registros, ensure_ascii=False).encode()
        linhas = [[item.get(campo) for campo in campos] for item in registros]
        return xlsx(campos, linhas) if formato == "xlsx" else csv_bytes(campos, linhas)

    def validar(self, modo, formato, registros, *, conteudo=None):
        conteudo = conteudo if conteudo is not None else self.conteudo(
            modo, formato, registros
        )
        return self.client.post(
            "/api/v1/meu-conteudo/importacoes/validar",
            data={"modo": modo},
            files={"arquivo": (f"lote.{formato}", conteudo)},
        )

    def confirmar(self, token, formato, conteudo):
        return self.client.post(
            "/api/v1/meu-conteudo/importacoes/confirmar",
            data={"token_preview": token},
            files={"arquivo": (f"lote.{formato}", conteudo)},
        )

    def quantidade(self, modelo):
        with self.sessions() as db:
            return db.scalar(select(func.count(modelo.id)))

    def test_endpoints_exigem_autenticacao(self):
        app.dependency_overrides.pop(usuario_atual)
        arquivo = json.dumps([self.classic_dict()]).encode()
        validar = self.client.post(
            "/api/v1/meu-conteudo/importacoes/validar",
            data={"modo": MODO_QUIZ_CLASSICO},
            files={"arquivo": ("lote.json", arquivo)},
        )
        confirmar = self.client.post(
            "/api/v1/meu-conteudo/importacoes/confirmar",
            data={"token_preview": "x"},
            files={"arquivo": ("lote.json", arquivo)},
        )
        self.assertEqual((validar.status_code, confirmar.status_code), (401, 401))

    def test_seis_formatos_preview_sem_escrita_e_confirmacao(self):
        for modo, modelo, registro in (
            (MODO_QUIZ_CLASSICO, Pergunta, self.classic_dict()),
            (MODO_NEM_A_PATO, PerguntaNemPato, self.np_dict()),
        ):
            for formato in ("xlsx", "csv", "json"):
                with self.subTest(modo=modo, formato=formato):
                    registro_atual = dict(registro)
                    registro_atual["enunciado"] = f"{modo}-{formato}"
                    conteudo = self.conteudo(modo, formato, [registro_atual])
                    antes = self.quantidade(modelo)
                    preview = self.validar(
                        modo, formato, [registro_atual], conteudo=conteudo
                    )
                    self.assertEqual(preview.status_code, 200, preview.text)
                    corpo = preview.json()
                    self.assertTrue(corpo["pode_confirmar"])
                    self.assertEqual(corpo["quantidade_valida"], 1)
                    self.assertEqual(self.quantidade(modelo), antes)
                    resposta = self.confirmar(
                        corpo["token_preview"], formato, conteudo
                    )
                    self.assertEqual(resposta.status_code, 200, resposta.text)
                    self.assertEqual(resposta.json()["criadas"], 1)
                    self.assertEqual(self.quantidade(modelo), antes + 1)

    def test_preview_erros_categoria_duplicidade_e_quota_nao_emite_token(self):
        alheia = self.categoria("Alheia", MODO_QUIZ_CLASSICO, usuario=self.outro)
        casos = (
            self.classic_dict(categoria_id=str(uuid4())),
            self.classic_dict(categoria_id=str(alheia.id)),
            self.classic_dict(categoria_id=str(self.np.id)),
        )
        for registro in casos:
            with self.subTest(registro=registro):
                resposta = self.validar(MODO_QUIZ_CLASSICO, "json", [registro])
                self.assertEqual(resposta.status_code, 200)
                self.assertFalse(resposta.json()["pode_confirmar"])
                self.assertIsNone(resposta.json()["token_preview"])

        duplicadas = [
            self.classic_dict(enunciado="Igual"),
            self.classic_dict(enunciado=" Igual "),
        ]
        resposta = self.validar(MODO_QUIZ_CLASSICO, "json", duplicadas)
        self.assertEqual(resposta.json()["erros"][0]["codigo"], "pergunta_duplicada")

    def test_soft_deleted_outro_usuario_oficial_e_categoria_diferente_nao_bloqueiam(self):
        outra_categoria = self.categoria("Outra", MODO_QUIZ_CLASSICO)
        with self.sessions() as db:
            db.add_all((
                Pergunta(
                    id=1, categoria_id=self.classica.id, enunciado="Repetida",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C",
                    alternativa_d="D", alternativa_correta=0, explicacao="E",
                    origem=ORIGEM_USUARIO, usuario_id=self.usuario.id, ativa=False,
                    excluida_em=datetime.now(timezone.utc),
                ),
                Pergunta(
                    id=2, categoria_id=outra_categoria.id, enunciado="Repetida",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C",
                    alternativa_d="D", alternativa_correta=0, explicacao="E",
                    origem=ORIGEM_USUARIO, usuario_id=self.usuario.id,
                ),
            ))
            db.commit()
        resposta = self.validar(
            MODO_QUIZ_CLASSICO, "json",
            [self.classic_dict(enunciado="Repetida")],
        )
        self.assertTrue(resposta.json()["pode_confirmar"])

    def test_limites_arquivo_quantidade_vazio_e_estrutura(self):
        grande = self.client.post(
            "/api/v1/meu-conteudo/importacoes/validar",
            data={"modo": MODO_QUIZ_CLASSICO},
            files={"arquivo": ("lote.json", b"x" * (5 * 1024 * 1024 + 1))},
        )
        self.assertEqual(grande.status_code, 413)
        self.assertEqual(
            self.validar(MODO_QUIZ_CLASSICO, "json", [], conteudo=b"").status_code,
            422,
        )
        muitos = [self.classic_dict(enunciado=f"Q{i}") for i in range(101)]
        self.assertEqual(
            self.validar(MODO_QUIZ_CLASSICO, "json", muitos).status_code, 422
        )
        inesperado = self.classic_dict(campo_errado="x")
        corpo = self.validar(MODO_QUIZ_CLASSICO, "json", [inesperado]).json()
        self.assertEqual(corpo["erros"][0]["codigo"], "campo_inesperado")

    def test_token_arquivo_alterado_assinatura_e_outro_usuario(self):
        conteudo = self.conteudo(MODO_QUIZ_CLASSICO, "json", [self.classic_dict()])
        token = self.validar(
            MODO_QUIZ_CLASSICO, "json", [self.classic_dict()], conteudo=conteudo
        ).json()["token_preview"]
        alterado = self.conteudo(
            MODO_QUIZ_CLASSICO, "json", [self.classic_dict(enunciado="Outra")]
        )
        self.assertEqual(self.confirmar(token, "json", alterado).status_code, 422)
        self.assertEqual(self.confirmar(token + "x", "json", conteudo).status_code, 422)
        app.dependency_overrides[usuario_atual] = lambda: self.outro
        self.assertEqual(self.confirmar(token, "json", conteudo).status_code, 422)

    def test_token_expirado_e_finalidade_errada(self):
        conteudo = self.conteudo(MODO_QUIZ_CLASSICO, "json", [self.classic_dict()])
        digest = __import__("hashlib").sha256(conteudo).hexdigest()
        agora = datetime.now(timezone.utc)

        def token(finalidade, expira):
            return jwt.encode({
                "sub": str(self.usuario.id), "iat": agora - timedelta(hours=1),
                "exp": expira, "finalidade": finalidade,
                "modo": MODO_QUIZ_CLASSICO, "formato": "json",
                "sha256": digest, "quantidade": 1,
                "versao": VERSAO_CONTRATO,
            }, obter_segredo_jwt(), algorithm=JWT_ALGORITHM)

        expirado = token(FINALIDADE_TOKEN, agora - timedelta(minutes=1))
        errado = token("outra_finalidade", agora + timedelta(minutes=5))
        self.assertEqual(self.confirmar(expirado, "json", conteudo).status_code, 422)
        self.assertEqual(self.confirmar(errado, "json", conteudo).status_code, 422)

        sem_expiracao = jwt.encode({
            "sub": str(self.usuario.id), "iat": agora,
            "finalidade": FINALIDADE_TOKEN, "modo": MODO_QUIZ_CLASSICO,
            "formato": "json", "sha256": digest, "quantidade": 1,
            "versao": VERSAO_CONTRATO,
        }, obter_segredo_jwt(), algorithm=JWT_ALGORITHM)
        self.assertEqual(
            self.confirmar(sem_expiracao, "json", conteudo).status_code, 422
        )

    def test_np_json_estrito_csv_digitos_e_xlsx_integral(self):
        invalidos = (True, "42", 42.0, -1, 2**63)
        for valor in invalidos:
            with self.subTest(valor=valor):
                corpo = self.validar(
                    MODO_NEM_A_PATO, "json",
                    [self.np_dict(resposta_numerica=valor)],
                ).json()
                self.assertFalse(corpo["pode_confirmar"])
        for valor in (0, 2**63 - 1):
            corpo = self.validar(
                MODO_NEM_A_PATO, "json",
                [self.np_dict(resposta_numerica=valor, enunciado=f"Q{valor}")],
            ).json()
            self.assertTrue(corpo["pode_confirmar"])

        csv_ok = self.validar(MODO_NEM_A_PATO, "csv", [self.np_dict()])
        self.assertTrue(csv_ok.json()["pode_confirmar"])
        for valor in ("+42", "42.0", "4e1", "-1"):
            resposta = self.validar(
                MODO_NEM_A_PATO, "csv", [self.np_dict(resposta_numerica=valor)]
            )
            self.assertFalse(resposta.json()["pode_confirmar"])
        xlsx_ok = self.validar(
            MODO_NEM_A_PATO, "xlsx", [self.np_dict(resposta_numerica=42.0)]
        )
        self.assertTrue(xlsx_ok.json()["pode_confirmar"])
        xlsx_fracao = self.validar(
            MODO_NEM_A_PATO, "xlsx", [self.np_dict(resposta_numerica=42.5)]
        )
        self.assertFalse(xlsx_fracao.json()["pode_confirmar"])

    def test_formula_xlsx_csv_encoding_json_invalido_e_chave_duplicada(self):
        formula = self.np_dict(resposta_numerica="=40+2")
        resposta = self.validar(MODO_NEM_A_PATO, "xlsx", [formula])
        self.assertEqual(resposta.json()["erros"][0]["codigo"], "formula_nao_permitida")
        self.assertEqual(
            self.validar(MODO_NEM_A_PATO, "csv", [], conteudo=b"\xff\xfe").status_code,
            422,
        )
        self.assertEqual(
            self.validar(MODO_NEM_A_PATO, "json", [], conteudo=b"{").status_code,
            422,
        )
        duplicada = (
            '[{"categoria_id":"%s","categoria_id":"%s"}]'
            % (self.np.id, self.np.id)
        ).encode()
        self.assertEqual(
            self.validar(MODO_NEM_A_PATO, "json", [], conteudo=duplicada).status_code,
            422,
        )
        profundo = (b"[" * 1100) + b"0" + (b"]" * 1100)
        resposta_profunda = self.validar(
            MODO_NEM_A_PATO, "json", [], conteudo=profundo
        )
        self.assertEqual(resposta_profunda.status_code, 200)
        self.assertFalse(resposta_profunda.json()["pode_confirmar"])
        self.assertIsNone(resposta_profunda.json()["token_preview"])

    def test_confirmacao_revalida_categoria_duplicidade_e_quota(self):
        conteudo = self.conteudo(MODO_QUIZ_CLASSICO, "json", [self.classic_dict()])
        token = self.validar(
            MODO_QUIZ_CLASSICO, "json", [self.classic_dict()], conteudo=conteudo
        ).json()["token_preview"]
        with self.sessions() as db:
            categoria = db.get(Categoria, self.classica.id)
            categoria.ativa = False
            db.commit()
        self.assertEqual(self.confirmar(token, "json", conteudo).status_code, 409)

    def test_quota_mudou_depois_do_preview(self):
        with self.sessions() as db:
            db.add_all(PerguntaNemPato(
                categoria_id=self.np.id, enunciado=f"Base {indice}",
                resposta_numerica=indice, explicacao="E", origem=ORIGEM_USUARIO,
                usuario_id=self.usuario.id,
            ) for indice in range(199))
            db.commit()
        registro = self.np_dict(enunciado="Importada")
        conteudo = self.conteudo(MODO_NEM_A_PATO, "json", [registro])
        token = self.validar(
            MODO_NEM_A_PATO, "json", [registro], conteudo=conteudo
        ).json()["token_preview"]
        with self.sessions() as db:
            db.add(PerguntaNemPato(
                categoria_id=self.np.id, enunciado="Concorrente",
                resposta_numerica=1, explicacao="E", origem=ORIGEM_USUARIO,
                usuario_id=self.usuario.id,
            ))
            db.commit()
        self.assertEqual(self.confirmar(token, "json", conteudo).status_code, 409)

    def test_falha_no_flush_desfaz_lote_inteiro(self):
        registros = [self.np_dict(enunciado=f"Rollback {i}") for i in range(3)]
        conteudo = self.conteudo(MODO_NEM_A_PATO, "json", registros)
        with self.sessions() as db:
            preview = meu_conteudo_importacoes_service.validar(
                db, self.usuario.id, MODO_NEM_A_PATO, "lote.json", conteudo
            )
        with self.sessions() as db, patch.object(
            db, "flush", side_effect=RuntimeError("falha no último passo")
        ):
            with self.assertRaisesRegex(RuntimeError, "último passo"):
                meu_conteudo_importacoes_service.confirmar(
                    db, self.usuario.id, preview.token_preview,
                    "lote.json", conteudo,
                )
        self.assertEqual(self.quantidade(PerguntaNemPato), 0)

    def test_ids_classic_formam_faixa_e_metadados_sao_forcados(self):
        registros = [self.classic_dict(enunciado=f"Q{i}") for i in range(3)]
        conteudo = self.conteudo(MODO_QUIZ_CLASSICO, "json", registros)
        preview = self.validar(
            MODO_QUIZ_CLASSICO, "json", registros, conteudo=conteudo
        ).json()
        resposta = self.confirmar(preview["token_preview"], "json", conteudo)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        with self.sessions() as db:
            perguntas = list(db.scalars(select(Pergunta).order_by(Pergunta.id)))
        self.assertEqual([p.id for p in perguntas], [1, 2, 3])
        self.assertTrue(all(
            p.origem == ORIGEM_USUARIO and p.usuario_id == self.usuario.id
            and p.ativa and p.excluida_em is None for p in perguntas
        ))

    def test_texto_gigante_e_alternativa_numerica_sao_erros_de_registro(self):
        casos = (
            self.classic_dict(enunciado="x" * 10_001),
            self.classic_dict(alternativa_correta=0),
        )
        for registro in casos:
            corpo = self.validar(MODO_QUIZ_CLASSICO, "json", [registro]).json()
            self.assertFalse(corpo["pode_confirmar"])
            self.assertIsNone(corpo["token_preview"])


if __name__ == "__main__":
    unittest.main()
