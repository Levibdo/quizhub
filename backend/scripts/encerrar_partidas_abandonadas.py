#!/usr/bin/env python3
"""Regulariza partidas abandonadas sem apagar ou recalcular dados históricos.

O modo padrão é exclusivamente de leitura. A execução exige IDs explícitos,
confirmação do banco, justificativa e caminho protegido para o relatório.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Iterable, Sequence
from uuid import UUID

from dotenv import dotenv_values
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_engine
from app.models import (
    JogadorPartidaNemPato,
    PalpiteNemPato,
    ParticipanteNemPato,
    Partida,
    PartidaNemPato,
    PartidaPergunta,
    Resposta,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import PartidaNemPatoStatus, SalaNemPatoStatus


LOCK_KEY = 0x51485F4142414E44  # "QH_ABAND"
DEFAULT_INACTIVITY_HOURS = 72


class MaintenanceError(RuntimeError):
    """Falha operacional segura para apresentação ao operador."""


@dataclass(frozen=True)
class RecordResult:
    tipo: str
    id: str
    elegivel: bool
    motivo: str
    estado_anterior: str
    estado_posterior: str
    ultima_atividade: str
    inatividade_horas: float
    relacionados: dict[str, object]


def _as_uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise MaintenanceError(f"{label} inválido: informe um UUID.") from exc


def _database_name(session: Session) -> str:
    return str(session.scalar(text("SELECT current_database()")))


def _database_now(session: Session) -> datetime:
    value = session.scalar(select(func.now()))
    if value is None:
        raise MaintenanceError("não foi possível obter o horário do banco")
    return value


def _classic_activity(session: Session, partida: Partida) -> tuple[datetime, dict[str, int]]:
    row = session.execute(
        select(
            func.max(PartidaPergunta.disponibilizada_em),
            func.max(Resposta.respondida_em),
            func.count(func.distinct(PartidaPergunta.id)),
            func.count(func.distinct(Resposta.id)),
        )
        .select_from(PartidaPergunta)
        .outerjoin(Resposta, Resposta.partida_pergunta_id == PartidaPergunta.id)
        .where(PartidaPergunta.partida_id == partida.id)
    ).one()
    last = max(item for item in (partida.iniciada_em, row[0], row[1]) if item is not None)
    return last, {"perguntas": int(row[2]), "respostas": int(row[3])}


def _room_activity(session: Session, sala: SalaNemPato) -> tuple[datetime, dict[str, object]]:
    participantes = session.execute(
        select(
            func.max(ParticipanteNemPato.entrou_em),
            func.max(ParticipanteNemPato.saiu_em),
            func.count(ParticipanteNemPato.id),
        ).where(ParticipanteNemPato.sala_id == sala.id)
    ).one()
    partidas = list(session.scalars(
        select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)
    ))
    partida_ids = [item.id for item in partidas]
    if partida_ids:
        rodadas = session.execute(
            select(
                func.max(RodadaNemPato.iniciada_em),
                func.max(RodadaNemPato.finalizada_em),
                func.count(RodadaNemPato.id),
            ).where(RodadaNemPato.partida_id.in_(partida_ids))
        ).one()
        palpites = int(session.scalar(
            select(func.count(PalpiteNemPato.id))
            .join(RodadaNemPato, RodadaNemPato.id == PalpiteNemPato.rodada_id)
            .where(RodadaNemPato.partida_id.in_(partida_ids))
        ) or 0)
        jogadores = int(session.scalar(
            select(func.count(JogadorPartidaNemPato.id))
            .where(JogadorPartidaNemPato.partida_id.in_(partida_ids))
        ) or 0)
    else:
        rodadas = (None, None, 0)
        palpites = jogadores = 0
    candidates = [sala.criada_em, participantes[0], participantes[1], rodadas[0], rodadas[1]]
    candidates.extend(item.iniciada_em for item in partidas)
    candidates.extend(item.finalizada_em for item in partidas)
    last = max(item for item in candidates if item is not None)
    active = [item for item in partidas if item.status == "EM_ANDAMENTO"]
    current_round = None
    if len(active) == 1 and active[0].rodada_atual:
        current_round = session.scalar(
            select(RodadaNemPato).where(
                RodadaNemPato.partida_id == active[0].id,
                RodadaNemPato.numero == active[0].rodada_atual,
            )
        )
    related: dict[str, object] = {
        "participantes": int(participantes[2]),
        "partidas": len(partidas),
        "partidas_em_andamento": len(active),
        "partida_ativa_id": str(active[0].id) if len(active) == 1 else None,
        "rodadas": int(rodadas[2]),
        "palpites": palpites,
        "jogadores": jogadores,
        "rodada_atual_id": current_round.id if current_round else None,
        "rodada_atual_estado": current_round.status if current_round else None,
    }
    return last, related


def _hours(now: datetime, last: datetime) -> float:
    return round((now - last).total_seconds() / 3600, 3)


def _eligible(now: datetime, last: datetime, cutoff: datetime) -> tuple[bool, str]:
    if last > now:
        return False, "última atividade está no futuro"
    if last > cutoff:
        return False, "inatividade inferior ao limite"
    return True, "inatividade confirmada"


def _inspect_classic(
    session: Session, partida_id: UUID, now: datetime, cutoff: datetime, execute: bool,
) -> RecordResult:
    query = select(Partida).where(Partida.id == partida_id)
    if execute:
        query = query.with_for_update()
    partida = session.scalar(query)
    if partida is None:
        raise MaintenanceError(f"partida clássica {partida_id} não encontrada")
    last, related = _classic_activity(session, partida)
    eligible, reason = _eligible(now, last, cutoff)
    if partida.status != "EM_ANDAMENTO":
        eligible, reason = False, f"estado atual é {partida.status}"
    after = "EXPIRADA" if eligible else partida.status
    if execute and eligible:
        partida.status = "EXPIRADA"
        partida.finalizada_em = now
        session.flush()
    return RecordResult(
        "PARTIDA_CLASSICA", str(partida.id), eligible, reason, partida.status if not execute or not eligible else "EM_ANDAMENTO",
        after, last.isoformat(), _hours(now, last), related,
    )


def _inspect_room(
    session: Session, room_id: UUID, now: datetime, cutoff: datetime, execute: bool,
    justification: str,
) -> RecordResult:
    query = select(SalaNemPato).where(SalaNemPato.id == room_id)
    if execute:
        query = query.with_for_update()
    sala = session.scalar(query)
    if sala is None:
        raise MaintenanceError(f"sala Nem a Pato {room_id} não encontrada")
    before = sala.status.value
    last, related = _room_activity(session, sala)
    eligible, reason = _eligible(now, last, cutoff)
    if before not in {"AGUARDANDO", "EM_PARTIDA"}:
        eligible, reason = False, f"estado atual é {before}"
    active_id = related["partida_ativa_id"]
    if before == "AGUARDANDO" and related["partidas_em_andamento"] != 0:
        eligible, reason = False, "sala aguardando possui partida ativa"
    if before == "EM_PARTIDA" and related["partidas_em_andamento"] != 1:
        eligible, reason = False, "sala em partida não possui exatamente uma partida ativa"
    if execute and eligible:
        if active_id:
            partida = session.scalar(
                select(PartidaNemPato)
                .where(PartidaNemPato.id == UUID(str(active_id)))
                .with_for_update()
            )
            if partida is None or partida.status != "EM_ANDAMENTO":
                raise MaintenanceError("partida Nem a Pato mudou durante a operação")
            partida.status = PartidaNemPatoStatus.CANCELADA
            partida.finalizada_em = now
            partida.motivo_encerramento = "EXPIRACAO_ADMINISTRATIVA"
        sala.status = SalaNemPatoStatus.ENCERRADA
        sala.encerrada_em = now
        sala.estado_versao += 1
        session.flush()
    return RecordResult(
        "SALA_NEM_A_PATO", str(sala.id), eligible, reason, before,
        "ENCERRADA" if eligible else before, last.isoformat(), _hours(now, last),
        {**related, "partida_estado_posterior": "CANCELADA" if eligible and active_id else None,
         "justificativa": justification if execute and eligible else None},
    )


def _all_ids(session: Session) -> tuple[list[UUID], list[UUID]]:
    classics = list(session.scalars(
        select(Partida.id).where(Partida.status == "EM_ANDAMENTO").order_by(Partida.iniciada_em, Partida.id)
    ))
    rooms = list(session.scalars(
        select(SalaNemPato.id)
        .where(SalaNemPato.status.in_(("AGUARDANDO", "EM_PARTIDA")))
        .order_by(SalaNemPato.criada_em, SalaNemPato.id)
    ))
    return classics, rooms


def run(
    session: Session, *, classic_ids: Iterable[UUID], room_ids: Iterable[UUID],
    inactivity_hours: int, execute: bool, justification: str,
    confirmed_database: str | None = None,
) -> dict[str, object]:
    database = _database_name(session)
    if execute and confirmed_database != database:
        raise MaintenanceError("o nome do banco não corresponde à confirmação operacional")
    if inactivity_hours < DEFAULT_INACTIVITY_HOURS:
        raise MaintenanceError("o limite mínimo permitido é 72 horas")
    if execute and len(justification.strip()) < 10:
        raise MaintenanceError("a execução exige justificativa administrativa")
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise MaintenanceError("a operação exige PostgreSQL")

    if execute:
        session.execute(select(func.pg_advisory_xact_lock(LOCK_KEY)))
    else:
        session.execute(text("SET TRANSACTION READ ONLY"))
    session.execute(text("SET LOCAL statement_timeout = '30s'"))
    now = _database_now(session)
    cutoff = now - timedelta(hours=inactivity_hours)
    results = [
        *(_inspect_classic(session, item, now, cutoff, execute) for item in classic_ids),
        *(_inspect_room(session, item, now, cutoff, execute, justification) for item in room_ids),
    ]
    if execute and any(not item.elegivel for item in results):
        raise MaintenanceError("a seleção contém registro não elegível; transação cancelada")
    return {
        "modo": "EXECUCAO" if execute else "DRY_RUN",
        "banco": database,
        "observado_em": now.isoformat(),
        "limite_inatividade_horas": inactivity_hours,
        "corte": cutoff.isoformat(),
        "justificativa": justification if execute else None,
        "registros": [asdict(item) for item in results],
    }


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path = path.resolve()
    if path.exists():
        raise MaintenanceError("o relatório já existe; recusando sobrescrita")
    if not path.parent.is_dir():
        raise MaintenanceError("o diretório do relatório não existe")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _replace_report(path: Path, payload: dict[str, object]) -> None:
    path = path.resolve()
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != (stat.S_IRUSR | stat.S_IWUSR):
        raise MaintenanceError("o relatório pendente protegido não está disponível")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classic-id", action="append", default=[])
    parser.add_argument("--room-id", action="append", default=[])
    parser.add_argument("--all-eligible", action="store_true", help="listar todos os candidatos; somente dry-run")
    parser.add_argument("--min-inactivity-hours", type=int, default=DEFAULT_INACTIVITY_HOURS)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-database")
    parser.add_argument("--justification", default="")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--env-file", type=Path, help="arquivo protegido contendo DATABASE_URL")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.execute and args.all_eligible:
        raise SystemExit("ERRO: --all-eligible não pode ser usado com --execute")
    if args.execute and (not args.report or (not args.classic_id and not args.room_id)):
        raise SystemExit("ERRO: execução exige --report e ao menos um ID explícito")
    classic_ids = [_as_uuid(item, "classic-id") for item in args.classic_id]
    room_ids = [_as_uuid(item, "room-id") for item in args.room_id]
    if args.env_file:
        database_url = dotenv_values(args.env_file).get("DATABASE_URL")
        if not isinstance(database_url, str) or not database_url.strip():
            raise SystemExit("ERRO: DATABASE_URL ausente no arquivo de ambiente")
        os.environ["DATABASE_URL"] = database_url.strip()
    engine = get_engine()
    try:
        with Session(engine) as session:
            if args.all_eligible:
                classic_ids, room_ids = _all_ids(session)
            payload = run(
                session, classic_ids=classic_ids, room_ids=room_ids,
                inactivity_hours=args.min_inactivity_hours, execute=args.execute,
                justification=args.justification, confirmed_database=args.confirm_database,
            )
            if args.execute:
                payload["transacao"] = "PENDENTE"
                _write_report(args.report, payload)
                try:
                    session.commit()
                except Exception:
                    payload["transacao"] = "REVERTIDA"
                    _replace_report(args.report, payload)
                    raise
                payload["transacao"] = "CONFIRMADA"
                _replace_report(args.report, payload)
            else:
                payload["transacao"] = "NAO_INICIADA"
                if args.report:
                    _write_report(args.report, payload)
                session.rollback()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except MaintenanceError as exc:
        print(f"ERRO: {exc}", file=os.sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
