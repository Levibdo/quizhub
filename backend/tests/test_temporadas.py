import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.ranking import listar_temporadas
from app.db.base import Base
from app.models import Temporada
from app.services.temporadas import (
    TemporadaAtivaAusente,
    TemporadaInexistente,
    TemporadaInvalida,
    TemporadasService,
)


class TestTemporadas(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.service = TemporadasService()
        self.now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.engine.dispose()

    def temporada(self, numero, status, *, inicio=None, fim=None):
        temporada = Temporada(
            id=uuid4(), numero=numero, nome=f"Temporada {numero}", status=status,
            inicia_em=inicio or self.now, encerra_em=fim,
        )
        return temporada

    def test_numero_positivo_unico_e_no_maximo_uma_ativa(self):
        with self.sessions() as session:
            session.add(self.temporada(1, "ATIVA"))
            session.commit()
            session.add(self.temporada(2, "ATIVA"))
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_resolve_ativa_numero_uuid_e_rejeita_inexistente(self):
        with self.sessions() as session:
            anterior = self.temporada(
                1, "ENCERRADA", inicio=self.now - timedelta(days=30), fim=self.now
            )
            atual = self.temporada(2, "ATIVA")
            session.add_all([anterior, atual])
            session.commit()
            self.assertEqual(self.service.resolver(session, None).id, atual.id)
            self.assertEqual(self.service.resolver(session, "1").id, anterior.id)
            self.assertEqual(self.service.resolver(session, str(atual.id)).id, atual.id)
            with self.assertRaises(TemporadaInexistente):
                self.service.resolver(session, "invalida")

    def test_listagem_publica_coloca_ativa_primeiro(self):
        with self.sessions() as session:
            session.add_all([
                self.temporada(1, "ENCERRADA", fim=self.now),
                self.temporada(2, "ATIVA"),
                self.temporada(3, "PLANEJADA", inicio=self.now + timedelta(days=30)),
            ])
            session.commit()
            resposta = listar_temporadas(db=session)
            self.assertEqual([item.numero for item in resposta], [2, 1])

    def test_ativacao_interna_encerra_atual_e_ativa_planejada(self):
        with self.sessions() as session:
            atual = self.temporada(1, "ATIVA")
            futura = self.temporada(
                2, "PLANEJADA", inicio=self.now + timedelta(days=1)
            )
            session.add_all([atual, futura])
            session.commit()
            ativada = self.service.ativar(
                session, futura.id,
                temporada_atual_id=atual.id,
                agora=self.now,
            )
            session.commit()
            self.assertEqual(ativada.status, "ATIVA")
            self.assertEqual(atual.status, "ENCERRADA")
            self.assertEqual(atual.encerra_em, self.now)

    def test_ativacao_rejeita_destino_nao_planejado_e_ausencia_de_ativa(self):
        with self.sessions() as session:
            encerrada = self.temporada(1, "ENCERRADA", fim=self.now)
            atual = self.temporada(2, "ATIVA")
            session.add_all([encerrada, atual])
            session.commit()
            with self.assertRaises(TemporadaInvalida):
                self.service.ativar(
                    session, encerrada.id,
                    temporada_atual_id=atual.id,
                    agora=self.now,
                )
            atual.status = "ENCERRADA"
            atual.encerra_em = self.now
            session.commit()
            with self.assertRaises(TemporadaAtivaAusente):
                self.service.ativa(session)


if __name__ == "__main__":
    unittest.main()
