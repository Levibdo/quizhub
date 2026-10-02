import importlib.util
import unittest
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import BigInteger, create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from unittest.mock import patch
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Categoria,
    JogadorPartidaNemPato,
    PalpiteNemPato,
    PartidaNemPato,
    ParticipanteNemPato,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import (
    PartidaNemPatoStatus,
    ParticipanteNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
    TipoFinalizacaoRodadaNemPato,
)


class NemAPatoDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    @staticmethod
    def categoria():
        return Categoria(id="geral", nome="Geral", ativa=True)

    @staticmethod
    def sala(codigo="NP123456", **kwargs):
        return SalaNemPato(codigo=codigo, **kwargs)

    @staticmethod
    def participante(sala_id, *, nome="Ana", ordem=1, token=b"a" * 32, **kwargs):
        return ParticipanteNemPato(
            sala_id=sala_id,
            nome=nome,
            ordem_entrada=ordem,
            token_hash=token,
            **kwargs,
        )

    @staticmethod
    def pergunta(**kwargs):
        dados = {
            "categoria_id": "geral",
            "enunciado": "Quantos itens há?",
            "resposta_numerica": 42,
            "explicacao": "Contagem de teste.",
        }
        dados.update(kwargs)
        return PerguntaNemPato(**dados)

    @staticmethod
    def partida(sala_id, **kwargs):
        dados = {"sala_id": sala_id, "categoria_id": "geral", "numero": 1}
        dados.update(kwargs)
        return PartidaNemPato(**dados)

    @staticmethod
    def jogador(partida_id, participante_id, *, nome="Ana", ordem=1, **kwargs):
        return JogadorPartidaNemPato(
            partida_id=partida_id,
            participante_id=participante_id,
            nome_snapshot=nome,
            ordem_circular=ordem,
            **kwargs,
        )

    @staticmethod
    def rodada(partida_id, pergunta_id, jogador_id, *, numero=1, **kwargs):
        return RodadaNemPato(
            partida_id=partida_id,
            pergunta_id=pergunta_id,
            numero=numero,
            jogador_inicial_id=jogador_id,
            **kwargs,
        )

    def criar_base(self, session):
        categoria = self.categoria()
        sala = self.sala()
        session.add_all([categoria, sala])
        session.flush()
        participante = self.participante(sala.id, eh_anfitriao=True)
        pergunta = self.pergunta()
        session.add_all([participante, pergunta])
        session.flush()
        partida = self.partida(sala.id)
        session.add(partida)
        session.flush()
        jogador = self.jogador(partida.id, participante.id)
        session.add(jogador)
        session.flush()
        rodada = self.rodada(partida.id, pergunta.id, jogador.id)
        session.add(rodada)
        session.flush()
        return sala, participante, pergunta, partida, jogador, rodada

    def assert_integrity_error(self, session, instance):
        session.add(instance)
        with self.assertRaises(IntegrityError):
            session.commit()
        session.rollback()


class TestNemAPatoMetadata(NemAPatoDatabaseTestCase):
    def test_entidades_colunas_tipos_e_fks(self):
        esperadas = {
            "perguntas_nem_pato",
            "salas_nem_pato",
            "participantes_nem_pato",
            "partidas_nem_pato",
            "jogadores_partida_nem_pato",
            "rodadas_nem_pato",
            "palpites_nem_pato",
        }
        self.assertTrue(esperadas.issubset(Base.metadata.tables))
        pergunta = Base.metadata.tables["perguntas_nem_pato"]
        self.assertIsInstance(pergunta.c.resposta_numerica.type, BigInteger)
        self.assertEqual(
            {fk.target_fullname for fk in pergunta.c.categoria_id.foreign_keys},
            {"categorias.id"},
        )
        self.assertEqual(
            {fk.target_fullname for fk in Base.metadata.tables["partidas_nem_pato"].c.categoria_id.foreign_keys},
            {"categorias.id"},
        )
        self.assertEqual(
            {fk.target_fullname for fk in Base.metadata.tables["rodadas_nem_pato"].c.jogador_inicial_id.foreign_keys},
            {"jogadores_partida_nem_pato.id"},
        )
        self.assertEqual(
            {fk.target_fullname for fk in Base.metadata.tables["palpites_nem_pato"].c.jogador_partida_id.foreign_keys},
            {"jogadores_partida_nem_pato.id"},
        )
        for tabela in esperadas:
            self.assertTrue(
                all(
                    column.type.timezone
                    for column in Base.metadata.tables[tabela].columns
                    if hasattr(column.type, "timezone")
                    and column.type.__class__.__name__ == "DateTime"
                )
            )

    def test_indices_unicos_parciais_e_constraints_de_dominio(self):
        pergunta = Base.metadata.tables["perguntas_nem_pato"]
        self.assertIn(
            "ix_perguntas_nem_pato_categoria_ativa",
            {index.name for index in pergunta.indexes},
        )
        participantes = Base.metadata.tables["participantes_nem_pato"]
        self.assertIn(
            "uq_participantes_nem_pato_anfitriao_ativo",
            {index.name for index in participantes.indexes},
        )
        partidas = Base.metadata.tables["partidas_nem_pato"]
        self.assertIn(
            "uq_partidas_nem_pato_sala_em_andamento",
            {index.name for index in partidas.indexes},
        )
        checks = {
            tabela: {
                str(constraint.sqltext)
                for constraint in Base.metadata.tables[tabela].constraints
                if hasattr(constraint, "sqltext")
            }
            for tabela in (
                "salas_nem_pato",
                "partidas_nem_pato",
                "rodadas_nem_pato",
                "palpites_nem_pato",
                "perguntas_nem_pato",
            )
        }
        self.assertIn("estado_versao >= 0", checks["salas_nem_pato"])
        self.assertIn("total_rodadas = 10", checks["partidas_nem_pato"])
        self.assertIn("duracao_rodada_segundos = 120", checks["partidas_nem_pato"])
        self.assertIn("numero BETWEEN 1 AND 10", checks["rodadas_nem_pato"])
        self.assertIn("valor >= 0", checks["palpites_nem_pato"])
        self.assertIn("resposta_numerica >= 0", checks["perguntas_nem_pato"])

    def test_strenum_e_constantes_mvp(self):
        self.assertEqual(SalaNemPatoStatus.AGUARDANDO, "AGUARDANDO")
        self.assertEqual(ParticipanteNemPatoStatus.ABANDONOU, "ABANDONOU")
        self.assertEqual(PartidaNemPatoStatus.CANCELADA, "CANCELADA")
        self.assertEqual(RodadaNemPatoStatus.RESULTADO, "RESULTADO")
        self.assertEqual(TipoFinalizacaoRodadaNemPato.SEM_PALPITE, "SEM_PALPITE")
        with Session(self.engine) as session:
            sala = self.sala()
            session.add(sala)
            session.commit()
            recuperada = session.scalar(
                select(SalaNemPato).where(SalaNemPato.id == sala.id)
            )
            self.assertIsInstance(recuperada.status, SalaNemPatoStatus)


class TestNemAPatoConstraints(NemAPatoDatabaseTestCase):
    def test_codigo_de_sala_unico(self):
        with Session(self.engine) as session:
            session.add_all([self.sala(), self.sala()])
            self.assert_integrity_error(session, self.sala())

    def test_nome_e_ordem_de_entrada_unicos_por_sala(self):
        with Session(self.engine) as session:
            sala = self.sala()
            session.add(sala)
            session.flush()
            session.add(self.participante(sala.id))
            session.commit()
            self.assert_integrity_error(
                session,
                self.participante(sala.id, nome="Ana", ordem=2, token=b"b" * 32),
            )
            self.assert_integrity_error(
                session,
                self.participante(sala.id, nome="Bia", ordem=1, token=b"c" * 32),
            )

    def test_apenas_um_anfitriao_ativo_por_sala_e_transferivel_apos_saida(self):
        with Session(self.engine) as session:
            sala = self.sala()
            session.add(sala)
            session.flush()
            anfitriao = self.participante(sala.id, eh_anfitriao=True)
            session.add(anfitriao)
            session.commit()
            self.assert_integrity_error(
                session,
                self.participante(
                    sala.id, nome="Bia", ordem=2, token=b"b" * 32, eh_anfitriao=True
                ),
            )
            anfitriao.status = ParticipanteNemPatoStatus.ABANDONOU
            novo = self.participante(
                sala.id, nome="Bia", ordem=2, token=b"b" * 32, eh_anfitriao=True
            )
            session.add(novo)
            session.commit()

    def test_uma_partida_em_andamento_por_sala(self):
        with Session(self.engine) as session:
            session.add(self.categoria())
            sala = self.sala()
            session.add(sala)
            session.flush()
            session.add(self.partida(sala.id))
            session.commit()
            self.assert_integrity_error(
                session,
                self.partida(sala.id, numero=2),
            )
            finalizada = self.partida(
                sala.id, numero=2, status=PartidaNemPatoStatus.FINALIZADA
            )
            session.add(finalizada)
            session.commit()

    def test_rodadas_unicas_por_numero_e_pergunta_e_numero_entre_1_e_10(self):
        with Session(self.engine) as session:
            _, _, pergunta, partida, jogador, rodada = self.criar_base(session)
            session.commit()
            self.assert_integrity_error(
                session,
                self.rodada(partida.id, pergunta.id, jogador.id, numero=2),
            )
            pergunta_2 = self.pergunta(enunciado="Outra contagem?")
            session.add(pergunta_2)
            session.commit()
            self.assert_integrity_error(
                session,
                self.rodada(partida.id, pergunta_2.id, jogador.id, numero=1),
            )
            self.assert_integrity_error(
                session,
                self.rodada(partida.id, pergunta_2.id, jogador.id, numero=0),
            )
            self.assert_integrity_error(
                session,
                self.rodada(partida.id, pergunta_2.id, jogador.id, numero=11),
            )

    def test_pergunta_e_palpite_rejeitam_valores_negativos(self):
        with Session(self.engine) as session:
            _, _, _, _, jogador, rodada = self.criar_base(session)
            session.commit()
            self.assert_integrity_error(
                session,
                self.pergunta(enunciado="Inválida", resposta_numerica=-1),
            )
            self.assert_integrity_error(
                session,
                PalpiteNemPato(
                    rodada_id=rodada.id,
                    jogador_partida_id=jogador.id,
                    ordem=1,
                    valor=-1,
                    client_action_id=uuid4(),
                ),
            )

    def test_palpite_exige_ordem_positiva_e_action_id_unico_na_rodada(self):
        with Session(self.engine) as session:
            _, _, _, _, jogador, rodada = self.criar_base(session)
            action_id = uuid4()
            session.add(
                PalpiteNemPato(
                    rodada_id=rodada.id,
                    jogador_partida_id=jogador.id,
                    ordem=1,
                    valor=10,
                    client_action_id=action_id,
                )
            )
            session.commit()
            self.assert_integrity_error(
                session,
                PalpiteNemPato(
                    rodada_id=rodada.id,
                    jogador_partida_id=jogador.id,
                    ordem=0,
                    valor=11,
                    client_action_id=uuid4(),
                ),
            )
            self.assert_integrity_error(
                session,
                PalpiteNemPato(
                    rodada_id=rodada.id,
                    jogador_partida_id=jogador.id,
                    ordem=2,
                    valor=11,
                    client_action_id=action_id,
                ),
            )

    def test_status_invalido_rejeitado_pelo_banco(self):
        with Session(self.engine) as session:
            sala, _, _, partida, jogador, _ = self.criar_base(session)
            session.commit()
            self.assert_integrity_error(
                session, self.sala("NP654321", status="INVALIDO")
            )
            self.assert_integrity_error(
                session,
                self.participante(
                    sala.id, nome="Bia", ordem=2, token=b"b" * 32, status="INVALIDO"
                ),
            )
            self.assert_integrity_error(
                session,
                self.partida(sala.id, numero=2, status="INVALIDO"),
            )
            outro_participante = self.participante(
                sala.id, nome="Bia", ordem=2, token=b"b" * 32
            )
            session.add(outro_participante)
            session.commit()
            self.assert_integrity_error(
                session,
                self.jogador(
                    partida.id,
                    outro_participante.id,
                    nome="Bia",
                    ordem=2,
                    status="INVALIDO",
                ),
            )
            outra_pergunta = self.pergunta(enunciado="Pergunta para status inválido")
            session.add(outra_pergunta)
            session.commit()
            self.assert_integrity_error(
                session,
                self.rodada(
                    partida.id,
                    outra_pergunta.id,
                    jogador.id,
                    numero=2,
                    status="INVALIDO",
                ),
            )
            self.assert_integrity_error(
                session,
                self.rodada(
                    partida.id,
                    outra_pergunta.id,
                    jogador.id,
                    numero=2,
                    tipo_finalizacao="INVALIDO",
                ),
            )


class TestMigration0009(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parents[1] / "alembic/versions/0009_nem_a_pato_fundacao.py"
        spec = importlib.util.spec_from_file_location("migration_0009", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)

    def test_revision_parent_and_upgrade_downgrade_preservam_categorias(self):
        self.assertEqual((self.migration.revision, self.migration.down_revision), ("0009", "0008"))
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                Categoria.__table__.create(connection)
                connection.execute(
                    Categoria.__table__.insert().values(
                        id="geral", nome="Geral", ativa=True
                    )
                )
                operations = Operations(MigrationContext.configure(connection))
                with patch.object(self.migration, "op", operations):
                    self.migration.upgrade()
                    tabelas = set(inspect(connection).get_table_names())
                    self.assertTrue(
                        {
                            "perguntas_nem_pato",
                            "salas_nem_pato",
                            "participantes_nem_pato",
                            "partidas_nem_pato",
                            "jogadores_partida_nem_pato",
                            "rodadas_nem_pato",
                            "palpites_nem_pato",
                        }.issubset(tabelas)
                    )
                    self.assertIn("categorias", tabelas)
                    self.migration.downgrade()
                    self.assertEqual(
                        set(inspect(connection).get_table_names()), {"categorias"}
                    )
                    self.assertEqual(
                        connection.execute(
                            Categoria.__table__.select().with_only_columns(
                                Categoria.__table__.c.id
                            )
                        ).scalar_one(),
                        "geral",
                    )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()