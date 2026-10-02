import hashlib
import hmac
import secrets
from collections.abc import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import ParticipanteNemPato, SalaNemPato
from app.nem_a_pato import (
    MAX_JOGADORES_NEM_A_PATO,
    ParticipanteNemPatoStatus,
    SalaNemPatoStatus,
)
from app.schemas.nem_a_pato import (
    ParticipanteSalaPublico,
    ParticipacaoSalaCriada,
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


def sala_publica(sala: SalaNemPato) -> SalaLobbyPublica:
    ativos = sorted(
        (
            item
            for item in sala.participantes
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
    def __init__(
        self,
        *,
        gerador_codigo: Callable[[], str] = gerar_codigo_sala,
        gerador_credencial: Callable[[], str] = gerar_credencial,
        tentativas_codigo: int = TENTATIVAS_CODIGO_SALA,
    ) -> None:
        self.gerador_codigo = gerador_codigo
        self.gerador_credencial = gerador_credencial
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
        sala, participante = self._obter_participante_autenticado(db, codigo, token)
        return SalaRecuperada(
            sala=sala_publica(sala),
            participante=participante_publico(participante),
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

            era_anfitriao = participante.eh_anfitriao
            participante.status = ParticipanteNemPatoStatus.ABANDONOU
            participante.eh_anfitriao = False
            participante.saiu_em = func.now()
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