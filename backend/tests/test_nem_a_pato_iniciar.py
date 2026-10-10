import hashlib
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.conteudo import (
    CATEGORIAS_OFICIAIS,
    MODO_NEM_A_PATO,
    ORIGEM_OFICIAL,
    ORIGEM_USUARIO,
)
from app.db.session import get_db
from app.main import app
from app.models import (
    Categoria,
    JogadorPartidaNemPato,
    PartidaNemPato,
    ParticipanteNemPato,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
    Usuario,
)
from app.nem_a_pato import (
    PartidaNemPatoStatus,
    ParticipanteNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
)
from app.services.salas_nem_a_pato import SalasNemAPatoService


class InicioNemAPatoTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as session:
            session.add_all([
                Categoria(id=CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral"], slug="geral", nome="Geral", modo=MODO_NEM_A_PATO, origem="OFICIAL", ativa=True),
                Categoria(id=CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["tecnologia"], slug="tecnologia", nome="Tecnologia", modo=MODO_NEM_A_PATO, origem="OFICIAL", ativa=True),
                Categoria(id=uuid4(), slug="inativa", nome="Inativa", modo=MODO_NEM_A_PATO, origem="OFICIAL", ativa=False),
            ])
            session.commit()
        self.counter = 0
        self.service = SalasNemAPatoService(
            gerador_codigo=self._code,
            gerador_credencial=self._token,
            selecionar_perguntas=lambda perguntas, quantidade: sorted(
                perguntas, key=lambda item: item.id
            )[:quantidade],
        )
        self.perguntas(12)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _code(self):
        self.counter += 1
        return f"NP{self.counter:04d}"

    def _token(self):
        self.counter += 1
        return f"token-{self.counter}"

    def perguntas(self, quantidade, *, ativas=True):
        with self.sessions() as session:
            session.add_all([
                PerguntaNemPato(
                    categoria_id=CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral" if indice % 2 else "tecnologia"],
                    enunciado=f"Pergunta numérica de teste {uuid4()}-{indice}",
                    resposta_numerica=indice,
                    explicacao="Explicação privada de teste.",
                    ativa=ativas,
                )
                for indice in range(quantidade)
            ])
            session.commit()

    def sala_com(self, nomes):
        with self.sessions() as session:
            host = self.service.criar(session, nomes[0])
        self.tokens_by_name = {nomes[0]: host.credencial_participante}
        for nome in nomes[1:]:
            with self.sessions() as session:
                membro = self.service.entrar(session, host.sala.codigo, nome)
                self.tokens_by_name[nome] = membro.credencial_participante
        return host

    def iniciar(self, host, service=None):
        with self.sessions() as session:
            return (service or self.service).iniciar(
                session, host.sala.codigo, host.credencial_participante
            )

    def contagens(self, sala_codigo):
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == sala_codigo))
            partida = session.scalar(
                select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)
            )
            jogadores = list(session.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
            )) if partida else []
            rodadas = list(session.scalars(
                select(RodadaNemPato)
                .where(RodadaNemPato.partida_id == partida.id)
                .order_by(RodadaNemPato.numero)
            )) if partida else []
            return sala, partida, jogadores, rodadas

    def client(self):
        def database_override():
            with self.sessions() as session:
                yield session
        app.dependency_overrides[get_db] = database_override
        return TestClient(app)


class TestInicioNemAPatoService(InicioNemAPatoTestCase):
    def test_inicio_usa_privadas_do_catalogo_e_rejeita_proveniencia_divergente(self):
        with self.sessions() as session:
            usuario = Usuario(
                nome="Dona do catálogo",
                email="privada-nem@example.com",
                senha_hash="hash",
            )
            session.add(usuario)
            session.flush()
            categoria_privada = Categoria(
                slug="privada-nem",
                nome="Privada Nem",
                modo=MODO_NEM_A_PATO,
                origem=ORIGEM_USUARIO,
                usuario_id=usuario.id,
                ativa=True,
            )
            session.add(categoria_privada)
            session.flush()
            perguntas_privadas = [PerguntaNemPato(
                categoria_id=categoria_privada.id,
                enunciado=f"Pergunta privada perfeitamente válida {indice}",
                resposta_numerica=123 + indice,
                explicacao="Elegível na C1.4.",
                origem=ORIGEM_USUARIO,
                usuario_id=usuario.id,
                ativa=True,
            ) for indice in range(10)]
            pergunta_oficial_em_categoria_privada = PerguntaNemPato(
                categoria_id=categoria_privada.id,
                enunciado="Pergunta oficial em categoria privada",
                resposta_numerica=456,
                explicacao="A categoria também precisa ser oficial.",
                origem=ORIGEM_OFICIAL,
                ativa=True,
            )
            pergunta_privada_em_categoria_oficial = PerguntaNemPato(
                categoria_id=CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral"],
                enunciado="Pergunta privada em categoria oficial",
                resposta_numerica=789,
                explicacao="A pergunta precisa ser oficial.",
                origem=ORIGEM_USUARIO,
                usuario_id=usuario.id,
                ativa=True,
            )
            categoria_inativa = session.scalar(select(Categoria).where(
                Categoria.slug == "inativa"
            ))
            pergunta_em_categoria_inativa = PerguntaNemPato(
                categoria_id=categoria_inativa.id,
                enunciado="Pergunta oficial em categoria inativa",
                resposta_numerica=987,
                explicacao="A categoria precisa estar ativa.",
                origem=ORIGEM_OFICIAL,
                ativa=True,
            )
            session.add_all((
                *perguntas_privadas,
                pergunta_oficial_em_categoria_privada,
                pergunta_privada_em_categoria_oficial,
                pergunta_em_categoria_inativa,
            ))
            session.commit()
            ids_privados = {pergunta.id for pergunta in perguntas_privadas}
            bloqueadas = {
                pergunta_oficial_em_categoria_privada.id,
                pergunta_privada_em_categoria_oficial.id,
                pergunta_em_categoria_inativa.id,
            }
            for pergunta in session.scalars(select(PerguntaNemPato).where(
                PerguntaNemPato.origem == ORIGEM_OFICIAL,
                PerguntaNemPato.categoria_id != categoria_inativa.id,
            )):
                pergunta.ativa = False
            session.commit()

        host = self.sala_com(["Levi", "Jorge", "Luana"])
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(
                SalaNemPato.codigo == host.sala.codigo
            ))
            usuario = session.scalar(select(Usuario).where(
                Usuario.email == "privada-nem@example.com"
            ))
            sala.catalogo_usuario_id = usuario.id
            session.commit()

        self.iniciar(host)
        _, _, _, rodadas = self.contagens(host.sala.codigo)
        self.assertEqual(
            {rodada.pergunta_id for rodada in rodadas}, ids_privados
        )
        self.assertTrue(bloqueadas.isdisjoint(
            {rodada.pergunta_id for rodada in rodadas}
        ))

    def test_partida_copia_proprietario_do_catalogo_da_sala(self):
        with self.sessions() as session:
            usuario = Usuario(
                nome="Conta", email="owner-inicio@example.com", senha_hash="hash"
            )
            session.add(usuario)
            session.commit()
            usuario_id = usuario.id
            host = self.service.criar(session, "Levi", usuario)
        self.tokens_by_name = {"Levi": host.credencial_participante}
        for nome in ("Jorge", "Luana"):
            with self.sessions() as session:
                entrada = self.service.entrar(session, host.sala.codigo, nome)
                self.tokens_by_name[nome] = entrada.credencial_participante

        self.iniciar(host)
        sala, partida, _, _ = self.contagens(host.sala.codigo)
        self.assertEqual(sala.catalogo_usuario_id, usuario_id)
        self.assertEqual(partida.catalogo_usuario_id, usuario_id)

    def test_host_inicia_com_tres_jogadores_e_prepara_partida_completa(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        resposta = self.iniciar(host)
        sala, partida, jogadores, rodadas = self.contagens(host.sala.codigo)

        self.assertEqual(sala.status, SalaNemPatoStatus.EM_PARTIDA)
        self.assertEqual(sala.estado_versao, 3)
        self.assertEqual(partida.status, PartidaNemPatoStatus.EM_ANDAMENTO)
        self.assertEqual((partida.numero, partida.rodada_atual), (1, 0))
        self.assertEqual((partida.total_rodadas, partida.duracao_rodada_segundos), (10, 120))
        self.assertEqual([j.nome_snapshot for j in jogadores], ["Levi", "Jorge", "Luana"])
        self.assertEqual([j.ordem_circular for j in jogadores], [1, 2, 3])
        self.assertEqual(len(rodadas), 10)
        self.assertEqual([r.numero for r in rodadas], list(range(1, 11)))
        self.assertEqual(len({r.pergunta_id for r in rodadas}), 10)
        with self.sessions() as session:
            categorias_rodadas = set(session.scalars(
                select(PerguntaNemPato.categoria_id)
                .join(RodadaNemPato, RodadaNemPato.pergunta_id == PerguntaNemPato.id)
                .where(RodadaNemPato.partida_id == partida.id)
            ))
        self.assertEqual(categorias_rodadas, {
            CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral"],
            CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["tecnologia"],
        })
        self.assertEqual([r.jogador_inicial_id for r in rodadas], [
            jogadores[0].id, jogadores[1].id, jogadores[2].id,
            jogadores[0].id, jogadores[1].id, jogadores[2].id,
            jogadores[0].id, jogadores[1].id, jogadores[2].id,
            jogadores[0].id,
        ])
        self.assertTrue(all(r.status == RodadaNemPatoStatus.AGUARDANDO_INICIO for r in rodadas))
        self.assertTrue(all(r.iniciada_em is None and r.termina_em is None for r in rodadas))
        self.assertEqual(resposta.partida.numero, 1)
        self.assertEqual([j.nome for j in resposta.partida.jogadores], ["Levi", "Jorge", "Luana"])

    def test_host_inicia_com_seis_e_inclui_somente_ativos_com_ordem_compactada(self):
        host = self.sala_com(["A", "B", "C", "D", "E", "F"])
        resposta = self.iniciar(host)
        _, _, jogadores, rodadas = self.contagens(host.sala.codigo)
        self.assertEqual(len(jogadores), 6)
        self.assertEqual([j.ordem_circular for j in jogadores], list(range(1, 7)))
        self.assertEqual(len(rodadas), 10)
        self.assertEqual(resposta.partida.numero, 1)

    def test_snapshot_omite_abandonado_e_compacta_ordem_circular(self):
        host = self.sala_com(["A", "B", "C", "D", "E", "F"])
        with self.sessions() as session:
            b = session.scalar(select(ParticipanteNemPato).where(
                ParticipanteNemPato.sala_id == session.scalar(
                    select(SalaNemPato.id).where(SalaNemPato.codigo == host.sala.codigo)
                ),
                ParticipanteNemPato.nome == "B",
            ))
            b.status = ParticipanteNemPatoStatus.ABANDONOU
            b.eh_anfitriao = False
            b.saiu_em = func.now()
            session.commit()
        # Host foi explicitamente transferido pelo service antes do start.
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            ativos = list(session.scalars(select(ParticipanteNemPato).where(
                ParticipanteNemPato.sala_id == sala.id,
                ParticipanteNemPato.status == ParticipanteNemPatoStatus.ATIVO,
            ).order_by(ParticipanteNemPato.ordem_entrada)))
            ativos[0].eh_anfitriao = True
            session.commit()
        resposta = self.iniciar(host)
        sala, partida, jogadores, rodadas = self.contagens(host.sala.codigo)
        self.assertEqual(len(jogadores), 5)
        self.assertEqual([j.nome_snapshot for j in jogadores], ["A", "C", "D", "E", "F"])
        self.assertEqual([j.ordem_circular for j in jogadores], [1, 2, 3, 4, 5])
        self.assertEqual(resposta.partida.numero, 1)
        self.assertEqual(len(rodadas), 10)

    def test_menos_de_tres_rejeita_sem_mudar_sala_ou_inserir_dados(self):
        host = self.sala_com(["Levi", "Jorge"])
        with self.sessions() as session:
            with self.assertRaises(Exception) as erro:
                self.service.iniciar(session, host.sala.codigo, host.credencial_participante)
        self.assertEqual(erro.exception.status_code, 409)
        self.assertIn("pelo menos 3", erro.exception.detail)
        sala, partida, jogadores, rodadas = self.contagens(host.sala.codigo)
        self.assertEqual(sala.status, SalaNemPatoStatus.AGUARDANDO)
        self.assertIsNone(partida)
        self.assertEqual((jogadores, rodadas), ([], []))

    def test_mais_de_seis_ativos_e_estado_invalido_rejeita(self):
        host = self.sala_com(["A", "B", "C"])
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            session.add_all([
                ParticipanteNemPato(
                    sala_id=sala.id,
                    nome=f"Extra {index}",
                    token_hash=hashlib.sha256(uuid4().bytes).digest(),
                    ordem_entrada=index + 4,
                    status=ParticipanteNemPatoStatus.ATIVO,
                )
                for index in range(4)
            ])
            session.commit()
        with self.sessions() as session:
            with self.assertRaises(Exception) as erro:
                self.service.iniciar(session, host.sala.codigo, host.credencial_participante)
        self.assertEqual(erro.exception.status_code, 409)
        self.assertIn("quantidade", erro.exception.detail)
        self.assertIsNone(self.contagens(host.sala.codigo)[1])

    def test_nao_host_token_invalido_abandonado_ou_outra_sala_nao_iniciam(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        with self.sessions() as session:
            with self.assertRaises(Exception) as erro:
                self.service.iniciar(session, host.sala.codigo, "token-invalido")
        self.assertEqual(erro.exception.status_code, 401)
        with self.sessions() as session:
            with self.assertRaises(Exception) as nao_host:
                self.service.iniciar(session, host.sala.codigo, self.tokens_by_name["Jorge"])
        self.assertEqual(nao_host.exception.status_code, 403)
        outra = self.sala_com(["Outra", "Pessoa", "Terceira"])
        with self.sessions() as session:
            with self.assertRaises(Exception) as cruzada:
                self.service.iniciar(session, host.sala.codigo, outra.credencial_participante)
        self.assertEqual(cruzada.exception.status_code, 401)
        with self.sessions() as session:
            membro = session.scalar(select(ParticipanteNemPato).where(
                ParticipanteNemPato.sala_id == session.scalar(
                    select(SalaNemPato.id).where(SalaNemPato.codigo == host.sala.codigo)
                ),
                ParticipanteNemPato.eh_anfitriao.is_(True),
            ))
            membro.status = ParticipanteNemPatoStatus.ABANDONOU
            membro.eh_anfitriao = False
            session.commit()
        with self.sessions() as session:
            with self.assertRaises(Exception) as abandonado:
                self.service.iniciar(session, host.sala.codigo, host.credencial_participante)
        self.assertEqual(abandonado.exception.status_code, 403)

    def test_sala_inexistente_fechada_ou_ja_iniciada_rejeita(self):
        with self.sessions() as session:
            with self.assertRaises(Exception) as ausente:
                self.service.iniciar(session, "ZZZZZZ", "no-token")
        self.assertEqual(ausente.exception.status_code, 404)
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        self.iniciar(host)
        with self.sessions() as session:
            with self.assertRaises(Exception) as repetido:
                self.service.iniciar(session, host.sala.codigo, host.credencial_participante)
        self.assertEqual(repetido.exception.status_code, 409)
        outra = self.sala_com(["A2", "B2", "C2"])
        with self.sessions() as session:
            sala_fechada = session.scalar(select(SalaNemPato).where(
                SalaNemPato.codigo == outra.sala.codigo
            ))
            sala_fechada.status = SalaNemPatoStatus.ENCERRADA
            session.commit()
        with self.sessions() as session:
            with self.assertRaises(Exception) as fechada:
                self.service.iniciar(session, outra.sala.codigo, outra.credencial_participante)
        self.assertEqual(fechada.exception.status_code, 409)

    def test_numero_partida_segue_historico_da_sala(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            session.add(PartidaNemPato(
                sala_id=sala.id,
                categoria_id=CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral"],
                numero=1,
                status=PartidaNemPatoStatus.FINALIZADA,
                rodada_atual=10,
                finalizada_em=func.now(),
            ))
            session.commit()
        partida = self.iniciar(host).partida
        self.assertEqual(partida.numero, 2)

    def test_menos_de_dez_perguntas_ativas_nao_inicia_e_ignora_inativas(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        with self.sessions() as session:
            session.execute(
                delete(PerguntaNemPato).where(PerguntaNemPato.ativa.is_(True))
            )
            session.commit()
        self.perguntas(9)
        self.perguntas(4, ativas=False)
        with self.sessions() as session:
            with self.assertRaises(Exception) as erro:
                self.service.iniciar(session, host.sala.codigo, host.credencial_participante)
        self.assertEqual(erro.exception.status_code, 409)
        self.assertIn("10 perguntas", erro.exception.detail)
        sala, partida, _, _ = self.contagens(host.sala.codigo)
        self.assertEqual(sala.status, SalaNemPatoStatus.AGUARDANDO)
        self.assertIsNone(partida)

    def test_falha_durante_geracao_faz_rollback_completo(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        service = SalasNemAPatoService(
            selecionar_perguntas=lambda _perguntas, _quantidade: (_ for _ in ()).throw(
                RuntimeError("falha de seleção simulada")
            )
        )
        with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "falha de seleção"):
                service.iniciar(session, host.sala.codigo, host.credencial_participante)
        sala, partida, jogadores, rodadas = self.contagens(host.sala.codigo)
        self.assertEqual(sala.status, SalaNemPatoStatus.AGUARDANDO)
        self.assertEqual(sala.estado_versao, 2)
        self.assertIsNone(partida)
        self.assertEqual((jogadores, rodadas), ([], []))

    def test_dto_nao_expoe_perguntas_respostas_explicacoes_ou_hashes(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        estado = self.iniciar(host)
        serializado = estado.model_dump_json()
        for campo in ("resposta_numerica", "explicacao", "token_hash", "pergunta_id", "enunciado"):
            self.assertNotIn(campo, serializado)
        self.assertNotIn("credencial_participante", serializado)

    def test_recuperar_apos_inicio_retorna_apenas_resumo_seguro_da_partida(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        self.iniciar(host)
        with self.sessions() as session:
            recuperada = self.service.recuperar(
                session, host.sala.codigo, host.credencial_participante
            )
        self.assertEqual(recuperada.sala.status, "EM_PARTIDA")
        self.assertEqual(recuperada.partida.numero, 1)
        self.assertEqual(len(recuperada.partida.jogadores), 3)
        dados = recuperada.model_dump_json()
        for proibido in ("pergunta_id", "resposta_numerica", "explicacao", "token_hash"):
            self.assertNotIn(proibido, dados)

    def test_host_pode_abandonar_antes_da_r1_e_transfere_host(self):
        host = self.sala_com(["Levi", "Jorge", "Luana", "Bia"])
        self.iniciar(host)
        with self.sessions() as session:
            estado = self.service.abandonar(
                session, host.sala.codigo, host.credencial_participante
            )
        self.assertEqual(next(p.nome for p in estado.participantes if p.eh_anfitriao), "Jorge")
        sala, _, jogadores, _ = self.contagens(host.sala.codigo)
        self.assertEqual(sala.status, SalaNemPatoStatus.EM_PARTIDA)
        self.assertEqual(
            next(j.status for j in jogadores if j.nome_snapshot == "Levi"),
            ParticipanteNemPatoStatus.ABANDONOU,
        )

    def test_abandono_antes_da_r1_com_menos_de_tres_cancela(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        self.iniciar(host)
        with self.sessions() as session:
            self.service.abandonar(
                session, host.sala.codigo, self.tokens_by_name["Luana"]
            )
        sala, partida, jogadores, _ = self.contagens(host.sala.codigo)
        self.assertEqual(sala.status, SalaNemPatoStatus.ENCERRADA)
        self.assertEqual(partida.status, PartidaNemPatoStatus.CANCELADA)
        self.assertEqual(partida.motivo_encerramento, "JOGADORES_INSUFICIENTES")
        self.assertEqual(
            next(j.status for j in jogadores if j.nome_snapshot == "Luana"),
            ParticipanteNemPatoStatus.ABANDONOU,
        )


class TestInicioNemAPatoApi(InicioNemAPatoTestCase):
    def test_endpoint_iniciar_autenticado_e_resposta_privada_segura(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        with self.client() as client:
            resposta = client.post(
                f"/api/v1/nem-pato/salas/{host.sala.codigo}/iniciar",
                headers={"X-Nem-Pato-Token": host.credencial_participante},
            )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        dados = resposta.json()
        self.assertEqual(dados["sala"]["status"], "EM_PARTIDA")
        self.assertEqual(dados["sala"]["versao"], 3)
        self.assertEqual(dados["partida"]["total_rodadas"], 10)
        self.assertEqual(len(dados["partida"]["jogadores"]), 3)
        for proibido in (
            "resposta_numerica", "explicacao", "token_hash", "pergunta_id", "enunciado"
        ):
            self.assertNotIn(proibido, resposta.text)
            recuperada = client.get(
                f"/api/v1/nem-pato/salas/{host.sala.codigo}/eu",
                headers={"X-Nem-Pato-Token": host.credencial_participante},
            )
            self.assertEqual(recuperada.status_code, 200, recuperada.text)
            self.assertEqual(recuperada.json()["partida"]["status"], "EM_ANDAMENTO")
            self.assertNotIn("resposta_numerica", recuperada.text)

    def test_endpoint_sem_token_nao_inicia(self):
        host = self.sala_com(["Levi", "Jorge", "Luana"])
        with self.client() as client:
            resposta = client.post(f"/api/v1/nem-pato/salas/{host.sala.codigo}/iniciar")
        self.assertEqual(resposta.status_code, 401)
        sala, partida, _, _ = self.contagens(host.sala.codigo)
        self.assertEqual(sala.status, SalaNemPatoStatus.AGUARDANDO)
        self.assertIsNone(partida)


if __name__ == "__main__":
    unittest.main()
