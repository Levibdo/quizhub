import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import OperacaoAdministrativa, Usuario
from app.services.seguranca_administrativa import sanitizar_detalhes_auditoria


ESTADOS_RECUPERAVEIS = {"FALHOU", "INTERROMPIDA"}


@dataclass(frozen=True)
class ResultadoIdempotente:
    operacao_id: UUID
    codigo: int
    resposta: dict[str, Any] | None
    reproduzido: bool


def _erro(status_code: int, codigo: str, mensagem: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"codigo": codigo, "mensagem": mensagem},
    )


def validar_chave_idempotencia(chave: str | None) -> str:
    if chave is None or not chave.strip():
        raise _erro(
            status.HTTP_428_PRECONDITION_REQUIRED,
            "CHAVE_IDEMPOTENCIA_OBRIGATORIA",
            "a chave de idempotência é obrigatória",
        )
    normalizada = chave.strip()
    if len(normalizada) > 200:
        raise _erro(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "CHAVE_IDEMPOTENCIA_INVALIDA",
            "a chave de idempotência excede 200 caracteres",
        )
    return normalizada


def hash_requisicao_canonica(
    pedido: Mapping[str, Any],
    *,
    recurso_tipo: str,
    recurso_id: str | UUID | None,
) -> str:
    envelope = {
        "pedido": pedido,
        "recurso_id": str(recurso_id) if recurso_id is not None else None,
        "recurso_tipo": recurso_tipo,
    }
    try:
        canonico = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as erro:
        raise ValueError("pedido não pode ser canonicalizado") from erro
    return hashlib.sha256(canonico).hexdigest()


def _chave_lock(administrador_id: UUID, tipo_operacao: str, chave: str) -> int:
    digest = hashlib.sha256(
        f"{administrador_id}:{tipo_operacao}:{chave}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _adquirir_lock_transacional(
    db: Session, administrador_id: UUID, tipo_operacao: str, chave: str
) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:chave)"),
            {"chave": _chave_lock(administrador_id, tipo_operacao, chave)},
        )


def _buscar(
    db: Session, administrador_id: UUID, tipo_operacao: str, chave: str,
    *, bloquear: bool = False,
) -> OperacaoAdministrativa | None:
    consulta = select(OperacaoAdministrativa).where(
        OperacaoAdministrativa.administrador_id == administrador_id,
        OperacaoAdministrativa.tipo_operacao == tipo_operacao,
        OperacaoAdministrativa.chave_idempotencia == chave,
    )
    if bloquear:
        consulta = consulta.with_for_update()
    return db.scalar(consulta)


def reservar_operacao(
    db: Session,
    *,
    administrador_id: UUID,
    tipo_operacao: str,
    recurso_tipo: str,
    recurso_id: str | UUID | None,
    chave_idempotencia: str | None,
    pedido: Mapping[str, Any],
    permitir_recuperacao: bool = False,
) -> tuple[OperacaoAdministrativa, bool]:
    """Reserva persistentemente uma execução; o chamador confirma a transação."""
    chave = validar_chave_idempotencia(chave_idempotencia)
    administrador = db.get(Usuario, administrador_id)
    if (
        administrador is None
        or not administrador.ativo
        or administrador.perfil != "ADMIN"
    ):
        raise _erro(
            status.HTTP_403_FORBIDDEN,
            "ADMINISTRADOR_NAO_AUTORIZADO",
            "a operação exige administrador ativo",
        )
    hash_pedido = hash_requisicao_canonica(
        pedido, recurso_tipo=recurso_tipo, recurso_id=recurso_id
    )
    _adquirir_lock_transacional(db, administrador_id, tipo_operacao, chave)
    # O advisory lock serializa reservas do mesmo escopo. Não bloqueamos a linha
    # aqui porque a transação de negócio pode estar atualizando-a; concorrentes
    # precisam ler EM_ANDAMENTO e receber 409 sem aguardar a operação longa.
    existente = _buscar(db, administrador_id, tipo_operacao, chave)
    if existente is None:
        existente = OperacaoAdministrativa(
            administrador_id=administrador_id,
            tipo_operacao=tipo_operacao,
            recurso_tipo=recurso_tipo,
            recurso_id=str(recurso_id) if recurso_id is not None else None,
            chave_idempotencia=chave,
            hash_requisicao=hash_pedido,
        )
        db.add(existente)
        db.flush()
        return existente, False
    if existente.hash_requisicao != hash_pedido:
        raise _erro(
            status.HTTP_409_CONFLICT,
            "CHAVE_IDEMPOTENCIA_REUTILIZADA",
            "a chave já foi usada para uma requisição diferente",
        )
    if existente.estado == "CONCLUIDA":
        return existente, True
    if existente.estado == "EM_ANDAMENTO":
        raise _erro(
            status.HTTP_409_CONFLICT,
            "OPERACAO_ADMINISTRATIVA_EM_ANDAMENTO",
            "a operação administrativa ainda está em andamento",
        )
    if existente.estado in ESTADOS_RECUPERAVEIS and permitir_recuperacao:
        existente.estado = "EM_ANDAMENTO"
        existente.codigo_resultado = None
        existente.resposta_sanitizada = None
        existente.concluida_em = None
        existente.atualizada_em = datetime.now(timezone.utc)
        existente.tentativas += 1
        db.flush()
        return existente, False
    raise _erro(
        status.HTTP_409_CONFLICT,
        "OPERACAO_ADMINISTRATIVA_REQUER_RECONCILIACAO",
        "a operação falhou ou foi interrompida e requer recuperação explícita",
    )


def marcar_operacoes_interrompidas(
    db: Session, *, anteriores_a: datetime
) -> int:
    registros = list(db.scalars(
        select(OperacaoAdministrativa)
        .where(
            OperacaoAdministrativa.estado == "EM_ANDAMENTO",
            OperacaoAdministrativa.atualizada_em < anteriores_a,
        )
        .with_for_update(skip_locked=True)
    ))
    agora = datetime.now(timezone.utc)
    for registro in registros:
        registro.estado = "INTERROMPIDA"
        registro.codigo_resultado = 500
        registro.resposta_sanitizada = {
            "codigo": "OPERACAO_INTERROMPIDA",
        }
        registro.atualizada_em = agora
        registro.concluida_em = agora
    return len(registros)


def _registrar_falha(
    fabrica: sessionmaker[Session], operacao_id: UUID, erro: Exception
) -> None:
    with fabrica.begin() as db:
        registro = db.scalar(
            select(OperacaoAdministrativa)
            .where(OperacaoAdministrativa.id == operacao_id)
            .with_for_update()
        )
        if registro is None or registro.estado != "EM_ANDAMENTO":
            return
        agora = datetime.now(timezone.utc)
        registro.estado = "FALHOU"
        registro.codigo_resultado = 500
        registro.resposta_sanitizada = sanitizar_detalhes_auditoria({
            "codigo": "OPERACAO_FALHOU",
            "tipo_erro": type(erro).__name__,
        })
        registro.atualizada_em = agora
        registro.concluida_em = agora


def executar_operacao_idempotente(
    fabrica: sessionmaker[Session],
    *,
    administrador_id: UUID,
    tipo_operacao: str,
    recurso_tipo: str,
    recurso_id: str | UUID | None,
    chave_idempotencia: str | None,
    pedido: Mapping[str, Any],
    executar: Callable[[Session], tuple[int, Mapping[str, Any] | None]],
    permitir_recuperacao: bool = False,
) -> ResultadoIdempotente:
    """Executa efeitos e conclusão atomicamente após uma reserva persistente."""
    with fabrica.begin() as db:
        registro, reproduzido = reservar_operacao(
            db,
            administrador_id=administrador_id,
            tipo_operacao=tipo_operacao,
            recurso_tipo=recurso_tipo,
            recurso_id=recurso_id,
            chave_idempotencia=chave_idempotencia,
            pedido=pedido,
            permitir_recuperacao=permitir_recuperacao,
        )
        operacao_id = registro.id
        if reproduzido:
            return ResultadoIdempotente(
                operacao_id=registro.id,
                codigo=registro.codigo_resultado or 200,
                resposta=registro.resposta_sanitizada,
                reproduzido=True,
            )

    try:
        with fabrica.begin() as db:
            registro = db.get(OperacaoAdministrativa, operacao_id)
            if registro is None or registro.estado != "EM_ANDAMENTO":
                raise RuntimeError("reserva idempotente não está executável")
            codigo, resposta = executar(db)
            sanitizada = sanitizar_detalhes_auditoria(resposta)
            agora = datetime.now(timezone.utc)
            registro.estado = "CONCLUIDA"
            registro.codigo_resultado = codigo
            registro.resposta_sanitizada = sanitizada
            registro.atualizada_em = agora
            registro.concluida_em = agora
        return ResultadoIdempotente(
            operacao_id=operacao_id,
            codigo=codigo,
            resposta=sanitizada,
            reproduzido=False,
        )
    except Exception as erro:
        _registrar_falha(fabrica, operacao_id, erro)
        raise
