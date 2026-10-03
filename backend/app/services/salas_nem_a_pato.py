import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DesafioNemPato,
    JogadorPartidaNemPato,
    PalpiteNemPato,
    PartidaNemPato,
    ParticipanteNemPato,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import (
    MAX_JOGADORES_NEM_A_PATO,
    MIN_JOGADORES_NEM_A_PATO,
    DURACAO_RODADA_NEM_A_PATO_SEGUNDOS,
    TOTAL_RODADAS_NEM_A_PATO,
    PartidaNemPatoStatus,
    ParticipanteNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
    TipoFinalizacaoRodadaNemPato,
)
from app.schemas.nem_a_pato import (
    JogadorPartidaNemPatoPublico,
    PalpiteNemPatoPublico,
    ParticipanteSalaPublico,
    PerguntaRodadaNemPatoPublica,
    PerguntaResultadoNemPatoPublica,
    PartidaNemPatoPublica,
    ParticipacaoSalaCriada,
    RodadaNemPatoPublica,
    ResultadoDesafioNemPatoPublico,
    ResultadoTimeoutNemPatoPublico,
    SalaLobbyPublica,
    SalaRecuperada,
)

ALFABETO_CODIGO_SALA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TAMANHO_CODIGO_SALA = 6
TENTATIVAS_CODIGO_SALA = 5
TAMANHO_MAXIMO_NOME = 100
HEADER_TOKEN_NEM_PATO = "X-Nem-Pato-Token"


def hash_credencial(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def gerar_credencial() -> str:
    return secrets.token_urlsafe(32)


def gerar_codigo_sala() -> str:
    return "".join(
        secrets.choice(ALFABETO_CODIGO_SALA)
        for _ in range(TAMANHO_CODIGO_SALA)
    )


def normalizar_nome(nome: str) -> str:
    if not isinstance(nome, str):
        raise HTTPException(status_code=422, detail="nome deve ser texto")
    nome = nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome não pode ser vazio")
    if len(nome) > TAMANHO_MAXIMO_NOME:
        raise HTTPException(
            status_code=422,
            detail=f"nome deve ter no máximo {TAMANHO_MAXIMO_NOME} caracteres",
        )
    return nome


def _chave_nome(nome: str) -> str:
    return nome.casefold()


def _constraint_name(error: IntegrityError) -> str | None:
    original = getattr(error, "orig", None)
    diagnostics = getattr(original, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def _unique_room_code_conflict(error: IntegrityError) -> bool:
    if _constraint_name(error) == "uq_salas_nem_pato_codigo":
        return True
    original = str(getattr(error, "orig", ""))
    return "UNIQUE constraint failed: salas_nem_pato.codigo" in original


def participante_publico(
    participante: ParticipanteNemPato,
) -> ParticipanteSalaPublico:
    return ParticipanteSalaPublico(
        id=participante.id,
        nome=participante.nome,
        ordem_entrada=participante.ordem_entrada,
        eh_anfitriao=participante.eh_anfitriao,
        status=participante.status.value,
    )


def sala_publica(
    sala: SalaNemPato,
    participantes: list[ParticipanteNemPato] | None = None,
) -> SalaLobbyPublica:
    participantes_sala = (
        participantes if participantes is not None else sala.participantes
    )
    ativos = sorted(
        (
            item
            for item in participantes_sala
            if item.status == ParticipanteNemPatoStatus.ATIVO
        ),
        key=lambda item: item.ordem_entrada,
    )
    return SalaLobbyPublica(
        codigo=sala.codigo,
        status=sala.status.value,
        versao=sala.estado_versao,
        criada_em=sala.criada_em,
        participantes=[participante_publico(item) for item in ativos],
        participantes_ativos=len(ativos),
        limite_jogadores=MAX_JOGADORES_NEM_A_PATO,
    )


class SalasNemAPatoService:
    @staticmethod
    def _agora_autoritativo(db: Session) -> datetime:
        if db.get_bind().dialect.name == "postgresql":
            return db.scalar(select(func.clock_timestamp()))
        return datetime.now(timezone.utc)

    def _finalizar_timeout_se_expirado(
        self,
        db: Session,
        sala: SalaNemPato,
        rodada: RodadaNemPato,
        jogadores: list[JogadorPartidaNemPato],
        palpites: list[PalpiteNemPato],
    ) -> bool:
        if (
            rodada.status != RodadaNemPatoStatus.EM_ANDAMENTO
            or rodada.termina_em is None
        ):
            return False
        agora = self._agora_autoritativo(db)
        prazo = rodada.termina_em
        agora_comparavel = (
            agora.replace(tzinfo=None)
            if prazo.tzinfo is None and agora.tzinfo is not None
            else agora
        )
        if agora_comparavel < prazo:
            return False
        ultimo_palpite = palpites[-1] if palpites else None
        if ultimo_palpite is None:
            rodada.tipo_finalizacao = TipoFinalizacaoRodadaNemPato.SEM_PALPITE
        else:
            rodada.tipo_finalizacao = TipoFinalizacaoRodadaNemPato.TEMPO_ESGOTADO
            for jogador in jogadores:
                if (
                    jogador.status == ParticipanteNemPatoStatus.ATIVO
                    and jogador.id != ultimo_palpite.jogador_partida_id
                ):
                    jogador.patos += 1
        rodada.status = RodadaNemPatoStatus.RESULTADO
        rodada.finalizada_em = agora
        rodada.jogador_da_vez_id = None
        sala.estado_versao += 1
        return True

    def __init__(
        self,
        *,
        gerador_codigo: Callable[[], str] = gerar_codigo_sala,
        gerador_credencial: Callable[[], str] = gerar_credencial,
        selecionar_perguntas: Callable[
            [list[PerguntaNemPato], int], list[PerguntaNemPato]
        ] | None = None,
        tentativas_codigo: int = TENTATIVAS_CODIGO_SALA,
    ) -> None:
        self.gerador_codigo = gerador_codigo
        self.gerador_credencial = gerador_credencial
        self.selecionar_perguntas = selecionar_perguntas
        self.tentativas_codigo = tentativas_codigo

    def criar(self, db: Session, nome: str) -> ParticipacaoSalaCriada:
        nome = normalizar_nome(nome)
        for tentativa in range(self.tentativas_codigo):
            sala = SalaNemPato(codigo=self.gerador_codigo())
            db.add(sala)
            try:
                # Inserir sala separadamente torna retry limitado a colisões de código.
                db.flush()
            except IntegrityError as erro:
                db.rollback()
                if _unique_room_code_conflict(erro) and tentativa + 1 < self.tentativas_codigo:
                    continue
                if _unique_room_code_conflict(erro):
                    raise HTTPException(
                        status_code=503,
                        detail="não foi possível gerar um código de sala único",
                    ) from erro
                raise HTTPException(
                    status_code=409, detail="não foi possível criar a sala"
                ) from erro
            except Exception:
                db.rollback()
                raise

            token = self.gerador_credencial()
            participante = ParticipanteNemPato(
                sala_id=sala.id,
                nome=nome,
                token_hash=hash_credencial(token),
                ordem_entrada=1,
                eh_anfitriao=True,
                status=ParticipanteNemPatoStatus.ATIVO,
            )
            db.add(participante)
            try:
                db.flush()
                db.commit()
            except IntegrityError as erro:
                db.rollback()
                raise HTTPException(
                    status_code=409, detail="não foi possível criar a sala"
                ) from erro
            except Exception:
                db.rollback()
                raise
            sala.participantes = [participante]
            return ParticipacaoSalaCriada(
                sala=sala_publica(sala),
                participante=participante_publico(participante),
                credencial_participante=token,
            )
        raise HTTPException(
            status_code=503, detail="não foi possível gerar um código de sala único"
        )

    @staticmethod
    def _sala_bloqueada(db: Session, codigo: str) -> SalaNemPato | None:
        return db.scalar(
            select(SalaNemPato)
            .where(SalaNemPato.codigo == codigo)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _participantes_bloqueados(
        db: Session, sala_id: UUID
    ) -> list[ParticipanteNemPato]:
        return list(
            db.scalars(
                select(ParticipanteNemPato)
                .where(ParticipanteNemPato.sala_id == sala_id)
                .order_by(ParticipanteNemPato.ordem_entrada)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    def _codigo_normalizado(codigo: str) -> str:
        return codigo.strip().upper()

    def entrar(
        self, db: Session, codigo: str, nome: str
    ) -> ParticipacaoSalaCriada:
        codigo = self._codigo_normalizado(codigo)
        nome = normalizar_nome(nome)
        try:
            sala = self._sala_bloqueada(db, codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            participantes = self._participantes_bloqueados(db, sala.id)
            if sala.status != SalaNemPatoStatus.AGUARDANDO:
                raise HTTPException(status_code=409, detail="sala não está aguardando")
            ativos = [
                item
                for item in participantes
                if item.status == ParticipanteNemPatoStatus.ATIVO
            ]
            if len(ativos) >= MAX_JOGADORES_NEM_A_PATO:
                raise HTTPException(status_code=409, detail="sala cheia")
            nome_normalizado = _chave_nome(nome)
            if any(_chave_nome(item.nome) == nome_normalizado for item in participantes):
                raise HTTPException(status_code=409, detail="nome já está em uso na sala")

            token = self.gerador_credencial()
            anfitriao = not any(item.eh_anfitriao for item in ativos)
            participante = ParticipanteNemPato(
                sala_id=sala.id,
                nome=nome,
                token_hash=hash_credencial(token),
                ordem_entrada=max(
                    (item.ordem_entrada for item in participantes), default=0
                )
                + 1,
                eh_anfitriao=anfitriao,
                status=ParticipanteNemPatoStatus.ATIVO,
            )
            db.add(participante)
            sala.estado_versao += 1
            db.flush()
            db.commit()
            participantes.append(participante)
            sala.participantes = participantes
            return ParticipacaoSalaCriada(
                sala=sala_publica(sala),
                participante=participante_publico(participante),
                credencial_participante=token,
            )
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as erro:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="conflito ao adicionar participante à sala"
            ) from erro
        except Exception:
            db.rollback()
            raise

    def _obter_participante_autenticado(
        self, db: Session, codigo: str, token: str
    ) -> tuple[SalaNemPato, ParticipanteNemPato]:
        if not token:
            raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
        digest = hash_credencial(token)
        participante = db.scalar(
            select(ParticipanteNemPato).where(
                ParticipanteNemPato.token_hash == digest
            )
        )
        if participante is None or not hmac.compare_digest(
            participante.token_hash, digest
        ):
            raise HTTPException(status_code=401, detail="credencial Nem a Pato inválida")
        if participante.status != ParticipanteNemPatoStatus.ATIVO:
            raise HTTPException(status_code=403, detail="participante não está ativo")
        sala = db.scalar(
            select(SalaNemPato)
            .where(SalaNemPato.id == participante.sala_id)
            .options(selectinload(SalaNemPato.participantes))
        )
        if sala is None:
            raise HTTPException(status_code=404, detail="sala inexistente")
        if sala.codigo != self._codigo_normalizado(codigo):
            raise HTTPException(status_code=403, detail="credencial não pertence a esta sala")
        return sala, participante

    @staticmethod
    def _jogador_publico(
        jogador: JogadorPartidaNemPato,
        participante_id: UUID,
    ) -> JogadorPartidaNemPatoPublico:
        return JogadorPartidaNemPatoPublico(
            id=jogador.id,
            nome=jogador.nome_snapshot,
            ordem_circular=jogador.ordem_circular,
            status=jogador.status.value,
            eh_eu=jogador.participante_id == participante_id,
            patos=jogador.patos,
        )

    def _partida_publica(
        self,
        db: Session,
        partida: PartidaNemPato,
        participante_id: UUID,
        jogadores: list[JogadorPartidaNemPato] | None = None,
    ) -> PartidaNemPatoPublica:
        jogadores_ordenados = sorted(
            jogadores if jogadores is not None else list(db.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
            )),
            key=lambda jogador: jogador.ordem_circular,
        )
        jogadores_por_id = {jogador.id: jogador for jogador in jogadores_ordenados}
        numero_rodada = partida.rodada_atual or 1
        rodada = db.scalar(
            select(RodadaNemPato).where(
                RodadaNemPato.partida_id == partida.id,
                RodadaNemPato.numero == numero_rodada,
            )
        )
        rodada_publica = None
        if rodada is not None:
            palpites = list(db.scalars(
                select(PalpiteNemPato)
                .where(PalpiteNemPato.rodada_id == rodada.id)
                .order_by(PalpiteNemPato.ordem)
            ))
            pergunta = None
            if rodada.status in (RodadaNemPatoStatus.EM_ANDAMENTO, RodadaNemPatoStatus.RESULTADO):
                pergunta_db = db.get(PerguntaNemPato, rodada.pergunta_id)
                pergunta_schema = PerguntaResultadoNemPatoPublica if rodada.status == RodadaNemPatoStatus.RESULTADO else PerguntaRodadaNemPatoPublica
                pergunta = pergunta_schema(
                    id=pergunta_db.id,
                    categoria_id=pergunta_db.categoria_id,
                    enunciado=pergunta_db.enunciado,
                    unidade=pergunta_db.unidade,
                    **({"resposta_numerica": pergunta_db.resposta_numerica, "explicacao": pergunta_db.explicacao} if rodada.status == RodadaNemPatoStatus.RESULTADO else {}),
                )
            jogador_inicial = jogadores_por_id[rodada.jogador_inicial_id]
            jogador_da_vez = (
                jogadores_por_id.get(rodada.jogador_da_vez_id)
                if rodada.jogador_da_vez_id is not None
                else None
            )
            desafio = db.scalar(select(DesafioNemPato).where(DesafioNemPato.rodada_id == rodada.id))
            resultado_desafio = None
            if desafio is not None:
                palpite_desafiado = next(item for item in palpites if item.id == desafio.palpite_desafiado_id)
                resultado_desafio = ResultadoDesafioNemPatoPublico(
                    desafiante=self._jogador_publico(jogadores_por_id[desafio.desafiante_jogador_partida_id], participante_id),
                    palpite_desafiado=PalpiteNemPatoPublico(
                        ordem=palpite_desafiado.ordem, valor=palpite_desafiado.valor,
                        jogador=self._jogador_publico(jogadores_por_id[palpite_desafiado.jogador_partida_id], participante_id),
                        criado_em=palpite_desafiado.criado_em,
                    ),
                    jogador_penalizado=self._jogador_publico(jogadores_por_id[desafio.jogador_penalizado_id], participante_id),
                    resolvido_em=desafio.resolvido_em,
                )
            resultado_timeout = None
            if rodada.tipo_finalizacao in (
                TipoFinalizacaoRodadaNemPato.TEMPO_ESGOTADO,
                TipoFinalizacaoRodadaNemPato.SEM_PALPITE,
            ):
                ultimo_palpite = palpites[-1] if palpites else None
                ultimo_publico = (
                    PalpiteNemPatoPublico(
                        ordem=ultimo_palpite.ordem,
                        valor=ultimo_palpite.valor,
                        jogador=self._jogador_publico(
                            jogadores_por_id[ultimo_palpite.jogador_partida_id],
                            participante_id,
                        ),
                        criado_em=ultimo_palpite.criado_em,
                    )
                    if ultimo_palpite is not None else None
                )
                resultado_timeout = ResultadoTimeoutNemPatoPublico(
                    ultimo_palpite=ultimo_publico,
                    autor_protegido=ultimo_publico.jogador if ultimo_publico else None,
                )
            rodada_publica = RodadaNemPatoPublica(
                id=rodada.id,
                numero=rodada.numero,
                status=rodada.status.value,
                pergunta=pergunta,
                jogador_inicial=self._jogador_publico(
                    jogador_inicial, participante_id
                ),
                jogador_da_vez=(
                    self._jogador_publico(jogador_da_vez, participante_id)
                    if jogador_da_vez is not None else None
                ),
                maior_palpite=palpites[-1].valor if palpites else None,
                palpites=[
                    PalpiteNemPatoPublico(
                        ordem=palpite.ordem,
                        valor=palpite.valor,
                        jogador=self._jogador_publico(
                            jogadores_por_id[palpite.jogador_partida_id],
                            participante_id,
                        ),
                        criado_em=palpite.criado_em,
                    )
                    for palpite in palpites
                ],
                iniciada_em=rodada.iniciada_em,
                termina_em=rodada.termina_em,
                finalizada_em=rodada.finalizada_em,
                tipo_finalizacao=rodada.tipo_finalizacao.value if rodada.tipo_finalizacao else None,
                resultado_desafio=resultado_desafio,
                resultado_timeout=resultado_timeout,
            )
        return PartidaNemPatoPublica(
            id=partida.id,
            numero=partida.numero,
            status=partida.status.value,
            rodada_atual=partida.rodada_atual,
            total_rodadas=partida.total_rodadas,
            duracao_rodada_segundos=partida.duracao_rodada_segundos,
            jogadores=[
                self._jogador_publico(jogador, participante_id)
                for jogador in jogadores_ordenados
            ],
            rodada=rodada_publica,
        )

    def iniciar(
        self, db: Session, codigo: str, token: str | None
    ) -> SalaRecuperada:
        codigo = self._codigo_normalizado(codigo)
        if not token:
            raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
        token_digest = hash_credencial(token)
        try:
            # Ordem de locks compartilhada com entrada/abandono: sala → participantes.
            sala = self._sala_bloqueada(db, codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            if sala.status != SalaNemPatoStatus.AGUARDANDO:
                raise HTTPException(status_code=409, detail="sala não está aguardando")

            participantes = self._participantes_bloqueados(db, sala.id)
            participante = next(
                (
                    item for item in participantes
                    if hmac.compare_digest(item.token_hash, token_digest)
                ),
                None,
            )
            if participante is None:
                raise HTTPException(status_code=401, detail="credencial Nem a Pato inválida")
            if participante.status != ParticipanteNemPatoStatus.ATIVO:
                raise HTTPException(status_code=403, detail="participante não está ativo")
            if not participante.eh_anfitriao:
                raise HTTPException(status_code=403, detail="somente o anfitrião pode iniciar")

            ativos = [
                item for item in participantes
                if item.status == ParticipanteNemPatoStatus.ATIVO
            ]
            if len(ativos) < MIN_JOGADORES_NEM_A_PATO:
                raise HTTPException(
                    status_code=409,
                    detail="são necessários pelo menos 3 participantes ativos para iniciar",
                )
            if len(ativos) > MAX_JOGADORES_NEM_A_PATO:
                raise HTTPException(
                    status_code=409,
                    detail="quantidade de participantes ativos inválida",
                )

            partida_ativa = db.scalar(
                select(PartidaNemPato.id)
                .where(
                    PartidaNemPato.sala_id == sala.id,
                    PartidaNemPato.status == PartidaNemPatoStatus.EM_ANDAMENTO,
                )
                .with_for_update()
            )
            if partida_ativa is not None:
                raise HTTPException(status_code=409, detail="a sala já possui uma partida em andamento")

            if self.selecionar_perguntas is None:
                # Sortear no banco e bloquear somente as dez perguntas escolhidas.
                perguntas = list(
                    db.scalars(
                        select(PerguntaNemPato)
                        .where(PerguntaNemPato.ativa.is_(True))
                        .order_by(func.random())
                        .limit(TOTAL_RODADAS_NEM_A_PATO)
                        .with_for_update()
                    )
                )
                ids_ativos = {pergunta.id for pergunta in perguntas}
            else:
                perguntas_ativas = list(
                    db.scalars(
                        select(PerguntaNemPato)
                        .where(PerguntaNemPato.ativa.is_(True))
                        .order_by(PerguntaNemPato.id)
                    )
                )
                if len(perguntas_ativas) < TOTAL_RODADAS_NEM_A_PATO:
                    raise HTTPException(
                        status_code=409,
                        detail="não há 10 perguntas Nem a Pato ativas disponíveis",
                    )
                perguntas = self.selecionar_perguntas(
                    perguntas_ativas, TOTAL_RODADAS_NEM_A_PATO
                )
                ids_ativos = {pergunta.id for pergunta in perguntas_ativas}
            if len(perguntas) < TOTAL_RODADAS_NEM_A_PATO:
                raise HTTPException(
                    status_code=409,
                    detail="não há 10 perguntas Nem a Pato ativas disponíveis",
                )
            if (
                len(perguntas) != TOTAL_RODADAS_NEM_A_PATO
                or len({pergunta.id for pergunta in perguntas}) != TOTAL_RODADAS_NEM_A_PATO
                or any(
                    not pergunta.ativa or pergunta.id not in ids_ativos
                    for pergunta in perguntas
                )
            ):
                raise HTTPException(
                    status_code=409,
                    detail="não foi possível selecionar 10 perguntas distintas",
                )

            numero_partida = (
                db.scalar(
                    select(func.max(PartidaNemPato.numero)).where(
                        PartidaNemPato.sala_id == sala.id
                    )
                )
                or 0
            ) + 1
            partida = PartidaNemPato(
                sala_id=sala.id,
                # A coluna requerida pelo schema 0009 serve de categoria-base;
                # cada rodada conserva sua própria categoria e a seleção pode variar.
                categoria_id=perguntas[0].categoria_id,
                numero=numero_partida,
                status=PartidaNemPatoStatus.EM_ANDAMENTO,
                rodada_atual=0,
                total_rodadas=TOTAL_RODADAS_NEM_A_PATO,
                duracao_rodada_segundos=DURACAO_RODADA_NEM_A_PATO_SEGUNDOS,
            )
            db.add(partida)
            db.flush()

            jogadores_partida = []
            for ordem_circular, membro in enumerate(
                sorted(ativos, key=lambda item: item.ordem_entrada), start=1
            ):
                jogador = JogadorPartidaNemPato(
                    partida_id=partida.id,
                    participante_id=membro.id,
                    nome_snapshot=membro.nome,
                    ordem_circular=ordem_circular,
                    status=ParticipanteNemPatoStatus.ATIVO,
                )
                jogadores_partida.append(jogador)
                db.add(jogador)
            db.flush()

            for numero_rodada, pergunta in enumerate(perguntas, start=1):
                indice_jogador_inicial = (numero_rodada - 1) % len(jogadores_partida)
                db.add(
                    RodadaNemPato(
                        partida_id=partida.id,
                        pergunta_id=pergunta.id,
                        numero=numero_rodada,
                        status=RodadaNemPatoStatus.AGUARDANDO_INICIO,
                        jogador_inicial_id=jogadores_partida[indice_jogador_inicial].id,
                        jogador_da_vez_id=None,
                        iniciada_em=None,
                        termina_em=None,
                        finalizada_em=None,
                        tipo_finalizacao=None,
                    )
                )

            # Última verificação defensiva antes do commit; o lock da sala
            # serializa entradas, inícios e as demais mutações do lobby.
            sala.status = SalaNemPatoStatus.EM_PARTIDA
            sala.estado_versao += 1
            db.flush()
            db.commit()

            return SalaRecuperada(
                sala=sala_publica(sala, ativos),
                participante=participante_publico(participante),
                partida=self._partida_publica(
                    db, partida, participante.id, jogadores_partida
                ),
            )
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as erro:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="conflito ao iniciar partida; atualize o estado da sala",
            ) from erro
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _participante_autenticado_bloqueado(
        participantes: list[ParticipanteNemPato],
        token_digest: bytes,
    ) -> ParticipanteNemPato:
        participante = next(
            (
                item for item in participantes
                if hmac.compare_digest(item.token_hash, token_digest)
            ),
            None,
        )
        if participante is None:
            raise HTTPException(
                status_code=401, detail="credencial Nem a Pato inválida"
            )
        if participante.status != ParticipanteNemPatoStatus.ATIVO:
            raise HTTPException(status_code=403, detail="participante não está ativo")
        return participante

    @staticmethod
    def _jogador_inicial_da_rodada(
        jogadores: list[JogadorPartidaNemPato],
        numero_rodada: int,
    ) -> JogadorPartidaNemPato:
        jogadores_ordenados = sorted(
            jogadores, key=lambda jogador: jogador.ordem_circular
        )
        if not jogadores_ordenados:
            raise HTTPException(
                status_code=409, detail="a partida não possui jogadores ativos"
            )
        indice = (numero_rodada - 1) % len(jogadores_ordenados)
        return jogadores_ordenados[indice]

    def iniciar_rodada(
        self, db: Session, codigo: str, token: str | None
    ) -> SalaRecuperada:
        codigo = self._codigo_normalizado(codigo)
        if not token:
            raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
        token_digest = hash_credencial(token)
        try:
            # Ordem global NP3–NP5:
            # sala → participantes → partida → rodada → snapshots → palpites.
            sala = self._sala_bloqueada(db, codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            participantes = self._participantes_bloqueados(db, sala.id)
            participante = self._participante_autenticado_bloqueado(
                participantes, token_digest
            )
            if not participante.eh_anfitriao:
                raise HTTPException(
                    status_code=403,
                    detail="somente o anfitrião pode iniciar a rodada",
                )
            if sala.status != SalaNemPatoStatus.EM_PARTIDA:
                raise HTTPException(
                    status_code=409, detail="sala não está em partida"
                )

            partida = db.scalar(
                select(PartidaNemPato)
                .where(PartidaNemPato.sala_id == sala.id)
                .order_by(PartidaNemPato.numero.desc())
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if partida is None or partida.status != PartidaNemPatoStatus.EM_ANDAMENTO:
                raise HTTPException(
                    status_code=409, detail="partida não está em andamento"
                )

            # A NP5 abre somente a primeira rodada pelo fluxo normal.
            rodada = db.scalar(
                select(RodadaNemPato)
                .where(
                    RodadaNemPato.partida_id == partida.id,
                    RodadaNemPato.numero == 1,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if rodada is None:
                raise HTTPException(status_code=409, detail="rodada não encontrada")
            if (
                partida.rodada_atual != 0
                or rodada.status != RodadaNemPatoStatus.AGUARDANDO_INICIO
            ):
                raise HTTPException(status_code=409, detail="rodada já iniciada")

            jogadores = list(db.scalars(
                select(JogadorPartidaNemPato)
                .where(
                    JogadorPartidaNemPato.partida_id == partida.id,
                    JogadorPartidaNemPato.status
                    == ParticipanteNemPatoStatus.ATIVO,
                )
                .order_by(JogadorPartidaNemPato.ordem_circular)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            jogador_inicial = self._jogador_inicial_da_rodada(
                jogadores, rodada.numero
            )
            agora = datetime.now(timezone.utc)
            rodada.jogador_inicial_id = jogador_inicial.id
            rodada.jogador_da_vez_id = jogador_inicial.id
            rodada.status = RodadaNemPatoStatus.EM_ANDAMENTO
            rodada.iniciada_em = agora
            rodada.termina_em = agora + timedelta(
                seconds=partida.duracao_rodada_segundos
            )
            partida.rodada_atual = rodada.numero
            sala.estado_versao += 1
            db.flush()
            db.commit()
            return self.recuperar(db, codigo, token)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as erro:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="conflito ao iniciar rodada; atualize o estado da sala",
            ) from erro
        except Exception:
            db.rollback()
            raise

    def palpitar(
        self,
        db: Session,
        codigo: str,
        rodada_id: int,
        token: str | None,
        valor: int,
        client_action_id: UUID,
    ) -> SalaRecuperada:
        codigo = self._codigo_normalizado(codigo)
        if not token:
            raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
        token_digest = hash_credencial(token)
        try:
            sala = self._sala_bloqueada(db, codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            participantes = self._participantes_bloqueados(db, sala.id)
            participante = self._participante_autenticado_bloqueado(
                participantes, token_digest
            )
            if sala.status != SalaNemPatoStatus.EM_PARTIDA:
                raise HTTPException(
                    status_code=409, detail="sala não está em partida"
                )

            partida = db.scalar(
                select(PartidaNemPato)
                .where(PartidaNemPato.sala_id == sala.id)
                .order_by(PartidaNemPato.numero.desc())
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if partida is None or partida.status != PartidaNemPatoStatus.EM_ANDAMENTO:
                raise HTTPException(
                    status_code=409, detail="partida não está em andamento"
                )

            rodada = db.scalar(
                select(RodadaNemPato)
                .where(
                    RodadaNemPato.id == rodada_id,
                    RodadaNemPato.partida_id == partida.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if rodada is None:
                raise HTTPException(
                    status_code=404, detail="rodada não pertence à partida"
                )
            if rodada.numero != partida.rodada_atual:
                raise HTTPException(
                    status_code=409, detail="rodada não é a rodada atual"
                )

            jogadores = list(db.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            palpites = list(db.scalars(
                select(PalpiteNemPato)
                .where(PalpiteNemPato.rodada_id == rodada.id)
                .order_by(PalpiteNemPato.ordem)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            jogador = next(
                (
                    item for item in jogadores
                    if item.participante_id == participante.id
                ),
                None,
            )
            if (
                jogador is None
                or jogador.status != ParticipanteNemPatoStatus.ATIVO
            ):
                raise HTTPException(
                    status_code=403, detail="sua participação não está mais ativa"
                )

            existente = next(
                (
                    palpite for palpite in palpites
                    if palpite.client_action_id == client_action_id
                ),
                None,
            )
            if existente is not None:
                if (
                    existente.jogador_partida_id != jogador.id
                    or existente.valor != valor
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="client_action_id já usado em outra ação",
                    )
                db.rollback()
                return self.recuperar(db, codigo, token)

            if self._finalizar_timeout_se_expirado(
                db, sala, rodada, jogadores, palpites
            ):
                db.flush()
                db.commit()
                return self.recuperar(db, codigo, token)

            if rodada.status != RodadaNemPatoStatus.EM_ANDAMENTO:
                raise HTTPException(
                    status_code=409, detail="esta rodada não aceita mais palpites"
                )
            if rodada.jogador_da_vez_id != jogador.id:
                raise HTTPException(status_code=409, detail="não é sua vez")
            maior_palpite = palpites[-1].valor if palpites else None
            if maior_palpite is not None and valor <= maior_palpite:
                raise HTTPException(
                    status_code=409,
                    detail=f"seu palpite precisa ser maior que {maior_palpite}",
                )

            palpite = PalpiteNemPato(
                rodada_id=rodada.id,
                jogador_partida_id=jogador.id,
                ordem=len(palpites) + 1,
                valor=valor,
                client_action_id=client_action_id,
            )
            db.add(palpite)
            jogadores_ativos = [
                item for item in jogadores
                if item.status == ParticipanteNemPatoStatus.ATIVO
            ]
            indice_atual = next(
                indice for indice, item in enumerate(jogadores_ativos)
                if item.id == jogador.id
            )
            proximo = jogadores_ativos[(indice_atual + 1) % len(jogadores_ativos)]
            rodada.jogador_da_vez_id = proximo.id
            sala.estado_versao += 1
            db.flush()
            db.commit()
            return self.recuperar(db, codigo, token)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as erro:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="conflito ao registrar palpite; atualize o estado da rodada",
            ) from erro
        except Exception:
            db.rollback()
            raise


    def desafiar(
        self,
        db: Session,
        codigo: str,
        rodada_id: int,
        token: str | None,
        client_action_id: UUID,
    ) -> SalaRecuperada:
        codigo = self._codigo_normalizado(codigo)
        if not token:
            raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
        token_digest = hash_credencial(token)
        try:
            # Mesma ordem do palpite: sala -> participantes -> partida -> rodada
            # -> snapshots -> palpites. O lock da rodada serializa as resolucoes.
            sala = self._sala_bloqueada(db, codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            participantes = self._participantes_bloqueados(db, sala.id)
            participante = self._participante_autenticado_bloqueado(
                participantes, token_digest
            )
            if sala.status != SalaNemPatoStatus.EM_PARTIDA:
                raise HTTPException(status_code=409, detail="sala não está em partida")

            partida = db.scalar(
                select(PartidaNemPato)
                .where(PartidaNemPato.sala_id == sala.id)
                .order_by(PartidaNemPato.numero.desc())
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if partida is None or partida.status != PartidaNemPatoStatus.EM_ANDAMENTO:
                raise HTTPException(status_code=409, detail="partida não está em andamento")

            rodada = db.scalar(
                select(RodadaNemPato)
                .where(
                    RodadaNemPato.id == rodada_id,
                    RodadaNemPato.partida_id == partida.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if rodada is None:
                raise HTTPException(status_code=404, detail="rodada não pertence à partida")
            if rodada.numero != partida.rodada_atual:
                raise HTTPException(status_code=409, detail="rodada não é a rodada atual")

            jogadores = list(db.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            palpites = list(db.scalars(
                select(PalpiteNemPato)
                .where(PalpiteNemPato.rodada_id == rodada.id)
                .order_by(PalpiteNemPato.ordem)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            jogador = next(
                (item for item in jogadores if item.participante_id == participante.id),
                None,
            )
            if jogador is None or jogador.status != ParticipanteNemPatoStatus.ATIVO:
                raise HTTPException(status_code=403, detail="sua participação não está mais ativa")

            desafio_existente = db.scalar(
                select(DesafioNemPato).where(DesafioNemPato.rodada_id == rodada.id)
            )
            if desafio_existente is not None:
                if (
                    desafio_existente.client_action_id == client_action_id
                    and desafio_existente.desafiante_jogador_partida_id == jogador.id
                ):
                    db.rollback()
                    return self.recuperar(db, codigo, token)
                raise HTTPException(status_code=409, detail="rodada já foi resolvida")

            acao_existente = db.scalar(
                select(DesafioNemPato).where(
                    DesafioNemPato.client_action_id == client_action_id
                )
            )
            if acao_existente is not None:
                raise HTTPException(
                    status_code=409,
                    detail="client_action_id já usado em outra ação",
                )
            if self._finalizar_timeout_se_expirado(
                db, sala, rodada, jogadores, palpites
            ):
                db.flush()
                db.commit()
                return self.recuperar(db, codigo, token)

            if rodada.status != RodadaNemPatoStatus.EM_ANDAMENTO:
                raise HTTPException(status_code=409, detail="esta rodada não aceita desafio")
            if not palpites:
                raise HTTPException(status_code=409, detail="não há palpite para desafiar")

            ultimo_palpite = palpites[-1]
            if ultimo_palpite.jogador_partida_id == jogador.id:
                raise HTTPException(
                    status_code=409,
                    detail="você não pode desafiar seu próprio palpite",
                )
            pergunta = db.get(PerguntaNemPato, rodada.pergunta_id)
            if pergunta is None:
                raise HTTPException(status_code=409, detail="pergunta da rodada não encontrada")
            penalizado = (
                next(item for item in jogadores if item.id == ultimo_palpite.jogador_partida_id)
                if ultimo_palpite.valor > pergunta.resposta_numerica
                else jogador
            )
            agora = self._agora_autoritativo(db)
            db.add(
                DesafioNemPato(
                    rodada_id=rodada.id,
                    desafiante_jogador_partida_id=jogador.id,
                    palpite_desafiado_id=ultimo_palpite.id,
                    jogador_penalizado_id=penalizado.id,
                    client_action_id=client_action_id,
                    resolvido_em=agora,
                )
            )
            penalizado.patos += 1
            rodada.status = RodadaNemPatoStatus.RESULTADO
            rodada.tipo_finalizacao = TipoFinalizacaoRodadaNemPato.DESAFIO
            rodada.finalizada_em = agora
            rodada.jogador_da_vez_id = None
            sala.estado_versao += 1
            db.flush()
            db.commit()
            return self.recuperar(db, codigo, token)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as erro:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="conflito ao resolver desafio; atualize o estado da rodada",
            ) from erro
        except Exception:
            db.rollback()
            raise


    def iniciar_proxima_rodada(
        self,
        db: Session,
        codigo: str,
        rodada_id: int,
        token: str | None,
    ) -> SalaRecuperada:
        codigo = self._codigo_normalizado(codigo)
        if not token:
            raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
        token_digest = hash_credencial(token)
        try:
            # Ordem: sala -> participantes -> partida -> rodadas (numero)
            # -> snapshots. Nao ha palpites novos nesta transicao.
            sala = self._sala_bloqueada(db, codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            participantes = self._participantes_bloqueados(db, sala.id)
            participante = self._participante_autenticado_bloqueado(
                participantes, token_digest
            )
            if not participante.eh_anfitriao:
                raise HTTPException(
                    status_code=403,
                    detail="somente o anfitrião pode iniciar a próxima rodada",
                )
            if sala.status != SalaNemPatoStatus.EM_PARTIDA:
                raise HTTPException(status_code=409, detail="sala não está em partida")

            partida = db.scalar(
                select(PartidaNemPato)
                .where(PartidaNemPato.sala_id == sala.id)
                .order_by(PartidaNemPato.numero.desc())
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if partida is None or partida.status != PartidaNemPatoStatus.EM_ANDAMENTO:
                raise HTTPException(status_code=409, detail="partida não está em andamento")

            numero_atual = partida.rodada_atual
            rodadas = list(db.scalars(
                select(RodadaNemPato)
                .where(
                    RodadaNemPato.partida_id == partida.id,
                    RodadaNemPato.numero.in_((numero_atual, numero_atual + 1)),
                )
                .order_by(RodadaNemPato.numero)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            rodada_atual = next(
                (item for item in rodadas if item.id == rodada_id), None
            )
            if rodada_atual is None or rodada_atual.numero != numero_atual:
                raise HTTPException(
                    status_code=409, detail="rodada não é a rodada atual"
                )
            if rodada_atual.status != RodadaNemPatoStatus.RESULTADO:
                raise HTTPException(
                    status_code=409, detail="rodada atual ainda não possui resultado"
                )
            if rodada_atual.numero >= partida.total_rodadas:
                raise HTTPException(
                    status_code=409, detail="não há próxima rodada disponível"
                )
            proxima = next(
                (item for item in rodadas if item.numero == numero_atual + 1), None
            )
            if proxima is None:
                raise HTTPException(
                    status_code=409, detail="próxima rodada não encontrada"
                )
            if proxima.status != RodadaNemPatoStatus.AGUARDANDO_INICIO:
                raise HTTPException(
                    status_code=409, detail="próxima rodada já iniciada"
                )

            jogadores = list(db.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            ativos = [
                item for item in jogadores
                if item.status == ParticipanteNemPatoStatus.ATIVO
            ]
            if len(ativos) < MIN_JOGADORES_NEM_A_PATO:
                raise HTTPException(
                    status_code=409,
                    detail="são necessários pelo menos 3 jogadores ativos para continuar",
                )
            jogador_inicial = self._jogador_inicial_da_rodada(
                ativos, proxima.numero
            )
            agora = datetime.now(timezone.utc)
            proxima.jogador_inicial_id = jogador_inicial.id
            proxima.jogador_da_vez_id = jogador_inicial.id
            proxima.status = RodadaNemPatoStatus.EM_ANDAMENTO
            proxima.iniciada_em = agora
            proxima.termina_em = agora + timedelta(
                seconds=partida.duracao_rodada_segundos
            )
            partida.rodada_atual = proxima.numero
            sala.estado_versao += 1
            db.flush()
            db.commit()
            return self.recuperar(db, codigo, token)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as erro:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="conflito ao iniciar próxima rodada; atualize o estado da sala",
            ) from erro
        except Exception:
            db.rollback()
            raise

    def _sincronizar_timeout(self, db: Session, codigo: str, token: str) -> None:
        codigo = self._codigo_normalizado(codigo)
        token_digest = hash_credencial(token)
        try:
            sala = self._sala_bloqueada(db, codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            participantes = self._participantes_bloqueados(db, sala.id)
            participante = next(
                (item for item in participantes if hmac.compare_digest(item.token_hash, token_digest)),
                None,
            )
            if participante is None:
                outra_sala = db.scalar(
                    select(ParticipanteNemPato.id).where(
                        ParticipanteNemPato.token_hash == token_digest
                    )
                )
                if outra_sala is not None:
                    raise HTTPException(
                        status_code=403, detail="credencial não pertence a esta sala"
                    )
                raise HTTPException(
                    status_code=401, detail="credencial Nem a Pato inválida"
                )
            if participante.status != ParticipanteNemPatoStatus.ATIVO:
                raise HTTPException(
                    status_code=403, detail="participante não está ativo"
                )
            if sala.status != SalaNemPatoStatus.EM_PARTIDA:
                db.rollback()
                return
            partida = db.scalar(
                select(PartidaNemPato)
                .where(
                    PartidaNemPato.sala_id == sala.id,
                    PartidaNemPato.status == PartidaNemPatoStatus.EM_ANDAMENTO,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if partida is None or partida.rodada_atual == 0:
                db.rollback()
                return
            rodada = db.scalar(
                select(RodadaNemPato)
                .where(
                    RodadaNemPato.partida_id == partida.id,
                    RodadaNemPato.numero == partida.rodada_atual,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            jogadores = list(db.scalars(
                select(JogadorPartidaNemPato)
                .where(JogadorPartidaNemPato.partida_id == partida.id)
                .order_by(JogadorPartidaNemPato.ordem_circular)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            palpites = list(db.scalars(
                select(PalpiteNemPato)
                .where(PalpiteNemPato.rodada_id == rodada.id)
                .order_by(PalpiteNemPato.ordem)
                .with_for_update()
                .execution_options(populate_existing=True)
            ))
            if self._finalizar_timeout_se_expirado(
                db, sala, rodada, jogadores, palpites
            ):
                db.flush()
                db.commit()
            else:
                db.rollback()
        except HTTPException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

    def estado_publico(self, db: Session, codigo: str) -> SalaLobbyPublica:
        codigo = self._codigo_normalizado(codigo)
        sala = db.scalar(
            select(SalaNemPato)
            .where(SalaNemPato.codigo == codigo)
            .options(selectinload(SalaNemPato.participantes))
        )
        if sala is None:
            raise HTTPException(status_code=404, detail="sala inexistente")
        return sala_publica(sala)

    def recuperar(
        self, db: Session, codigo: str, token: str
    ) -> SalaRecuperada:
        if not token:
            raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
        self._sincronizar_timeout(db, codigo, token)
        sala, participante = self._obter_participante_autenticado(db, codigo, token)
        partida = None
        if sala.status == SalaNemPatoStatus.EM_PARTIDA:
            partida_db = db.scalar(
                select(PartidaNemPato)
                .where(
                    PartidaNemPato.sala_id == sala.id,
                    PartidaNemPato.status == PartidaNemPatoStatus.EM_ANDAMENTO,
                )
                .options(selectinload(PartidaNemPato.jogadores))
            )
            if partida_db is not None:
                partida = self._partida_publica(
                    db, partida_db, participante.id
                )
        return SalaRecuperada(
            sala=sala_publica(sala),
            participante=participante_publico(participante),
            partida=partida,
        )

    def abandonar(
        self, db: Session, codigo: str, token: str
    ) -> SalaLobbyPublica:
        sala, participante = self._obter_participante_autenticado(db, codigo, token)
        try:
            # Ordem global de lock: sala primeiro, depois todas as participações.
            sala = self._sala_bloqueada(db, sala.codigo)
            if sala is None:
                raise HTTPException(status_code=404, detail="sala inexistente")
            participantes = self._participantes_bloqueados(db, sala.id)
            participante = next(
                (item for item in participantes if item.id == participante.id), None
            )
            if participante is None or participante.status != ParticipanteNemPatoStatus.ATIVO:
                raise HTTPException(status_code=403, detail="participante não está ativo")

            jogador_partida = None
            if sala.status == SalaNemPatoStatus.EM_PARTIDA:
                partida = db.scalar(
                    select(PartidaNemPato)
                    .where(
                        PartidaNemPato.sala_id == sala.id,
                        PartidaNemPato.status == PartidaNemPatoStatus.EM_ANDAMENTO,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if partida is None or partida.rodada_atual == 0:
                    raise HTTPException(
                        status_code=409,
                        detail="abandono só é permitido entre rodadas",
                    )
                rodada = db.scalar(
                    select(RodadaNemPato)
                    .where(
                        RodadaNemPato.partida_id == partida.id,
                        RodadaNemPato.numero == partida.rodada_atual,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if rodada is None or rodada.status != RodadaNemPatoStatus.RESULTADO:
                    raise HTTPException(
                        status_code=409,
                        detail="abandono só é permitido entre rodadas",
                    )
                jogadores = list(
                    db.scalars(
                        select(JogadorPartidaNemPato)
                        .where(JogadorPartidaNemPato.partida_id == partida.id)
                        .order_by(JogadorPartidaNemPato.ordem_circular)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                )
                jogador_partida = next(
                    (item for item in jogadores if item.participante_id == participante.id),
                    None,
                )
                if jogador_partida is None:
                    raise HTTPException(
                        status_code=409,
                        detail="participante não pertence à partida atual",
                    )
            elif sala.status != SalaNemPatoStatus.AGUARDANDO:
                raise HTTPException(
                    status_code=409,
                    detail="abandono indisponível no estado atual da sala",
                )

            era_anfitriao = participante.eh_anfitriao
            participante.status = ParticipanteNemPatoStatus.ABANDONOU
            participante.eh_anfitriao = False
            participante.saiu_em = func.now()
            if jogador_partida is not None:
                jogador_partida.status = ParticipanteNemPatoStatus.ABANDONOU
                jogador_partida.saiu_em = func.now()
            # Uma ação de abandono incrementa a versão uma única vez, mesmo com handoff.
            sala.estado_versao += 1
            db.flush()
            if era_anfitriao:
                novo_anfitriao = next(
                    (
                        item
                        for item in participantes
                        if item.id != participante.id
                        and item.status == ParticipanteNemPatoStatus.ATIVO
                    ),
                    None,
                )
                if novo_anfitriao is not None:
                    novo_anfitriao.eh_anfitriao = True
            db.flush()
            db.commit()
            sala.participantes = participantes
            return sala_publica(sala)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as erro:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="conflito ao abandonar a sala"
            ) from erro
        except Exception:
            db.rollback()
            raise


salas_nem_a_pato = SalasNemAPatoService()


def obter_participante_por_token(db: Session, token: str | None) -> ParticipanteNemPato:
    if not token:
        raise HTTPException(status_code=401, detail="credencial Nem a Pato ausente")
    digest = hash_credencial(token)
    participante = db.scalar(
        select(ParticipanteNemPato).where(ParticipanteNemPato.token_hash == digest)
    )
    if participante is None or not hmac.compare_digest(participante.token_hash, digest):
        raise HTTPException(status_code=401, detail="credencial Nem a Pato inválida")
    if participante.status != ParticipanteNemPatoStatus.ATIVO:
        raise HTTPException(status_code=403, detail="participante não está ativo")
    return participante
