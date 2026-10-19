import unittest
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import (
    Categoria, Jogador, Partida, PartidaNemPato, Pergunta, PerguntaNemPato,
    RodadaNemPato, SalaNemPato,
)
from app.services.partidas import PartidasPersistentes
from app.services.salas_nem_a_pato import SalasNemAPatoService


class TestBloqueioSemCatalogoAtivo(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            classica = Categoria(
                slug="geral", nome="Geral", modo="QUIZ_CLASSICO",
                origem="OFICIAL", ativa=True,
            )
            nem = Categoria(
                slug="macabro", nome="Macabro", modo="NEM_A_PATO",
                origem="OFICIAL", ativa=True,
            )
            db.add_all([classica, nem]); db.flush()
            db.add_all([
                Pergunta(
                    id=i, categoria_id=classica.id, enunciado=f"Legada {i}?",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C",
                    alternativa_d="D", alternativa_correta=0,
                    explicacao="Legada", origem="OFICIAL", ativa=True,
                ) for i in range(1, 11)
            ])
            db.add_all([
                PerguntaNemPato(
                    categoria_id=nem.id, enunciado=f"Legada numérica {i}?",
                    resposta_numerica=i, explicacao="Legada",
                    origem="OFICIAL", ativa=True,
                ) for i in range(1, 11)
            ])
            db.commit()
        self.nem = SalasNemAPatoService(
            gerador_codigo=lambda: "SEMATO",
            gerador_credencial=lambda: str(uuid4()),
            selecionar_perguntas=lambda itens, quantidade: itens[:quantidade],
        )

    def tearDown(self):
        self.engine.dispose()

    @staticmethod
    def assert_bloqueio(contexto):
        erro = contexto.exception
        assert isinstance(erro, HTTPException)
        assert erro.status_code == 503
        assert erro.detail["codigo"] == "CATALOGO_OFICIAL_INATIVO"

    def test_classico_bloqueia_antes_de_criar_registros(self):
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as contexto:
                PartidasPersistentes().criar(db, "Visitante", "geral")
            self.assert_bloqueio(contexto)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count(Jogador.id))), 0)
            self.assertEqual(db.scalar(select(func.count(Partida.id))), 0)

    def test_nem_pato_permite_lobby_mas_bloqueia_inicio_sem_estado_parcial(self):
        with self.sessions() as db:
            host = self.nem.criar(db, "A")
        tokens = [host.credencial_participante]
        for nome in ("B", "C"):
            with self.sessions() as db:
                tokens.append(self.nem.entrar(db, host.sala.codigo, nome).credencial_participante)
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as contexto:
                self.nem.iniciar(db, host.sala.codigo, tokens[0])
            self.assert_bloqueio(contexto)
        with self.sessions() as db:
            sala = db.scalar(select(SalaNemPato).where(SalaNemPato.codigo == "SEMATO"))
            self.assertEqual(sala.status.value, "AGUARDANDO")
            self.assertEqual(db.scalar(select(func.count(PartidaNemPato.id))), 0)
            self.assertEqual(db.scalar(select(func.count(RodadaNemPato.id))), 0)


if __name__ == "__main__":
    unittest.main()
