from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.nem_a_pato import (
    DURACAO_RODADA_NEM_A_PATO_SEGUNDOS,
    TOTAL_RODADAS_NEM_A_PATO,
    PartidaNemPatoStatus,
    ParticipanteNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
    TipoFinalizacaoRodadaNemPato,
)

if TYPE_CHECKING:
    from app.models.categoria import Categoria


def _enum_string(enum_type: type, length: int) -> SqlEnum:
    return SqlEnum(
        enum_type,
        native_enum=False,
        create_constraint=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class PerguntaNemPato(Base):
    __tablename__ = "perguntas_nem_pato"
    __table_args__ = (
        CheckConstraint(
            "resposta_numerica >= 0",
            name="ck_perguntas_nem_pato_resposta_nao_negativa",
        ),
        CheckConstraint(
            "length(trim(enunciado)) > 0",
            name="ck_perguntas_nem_pato_enunciado_nao_vazio",
        ),
        Index("ix_perguntas_nem_pato_categoria_ativa", "categoria_id", "ativa"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    categoria_id: Mapped[str] = mapped_column(
        String, ForeignKey("categorias.id"), nullable=False
    )
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    resposta_numerica: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unidade: Mapped[str | None] = mapped_column(String, nullable=True)
    explicacao: Mapped[str] = mapped_column(Text, nullable=False)
    fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    categoria: Mapped["Categoria"] = relationship(
        back_populates="perguntas_nem_pato"
    )
    rodadas: Mapped[list["RodadaNemPato"]] = relationship(
        back_populates="pergunta"
    )


class SalaNemPato(Base):
    __tablename__ = "salas_nem_pato"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AGUARDANDO', 'EM_PARTIDA', 'ENCERRADA')",
            name="ck_salas_nem_pato_status",
        ),
        CheckConstraint(
            "estado_versao >= 0", name="ck_salas_nem_pato_estado_versao_nao_negativo"
        ),
        CheckConstraint(
            "length(trim(codigo)) > 0", name="ck_salas_nem_pato_codigo_nao_vazio"
        ),
        UniqueConstraint("codigo", name="uq_salas_nem_pato_codigo"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[SalaNemPatoStatus] = mapped_column(
        _enum_string(SalaNemPatoStatus, 24),
        nullable=False,
        default=SalaNemPatoStatus.AGUARDANDO,
        server_default=text("'AGUARDANDO'"),
    )
    estado_versao: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    encerrada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    participantes: Mapped[list["ParticipanteNemPato"]] = relationship(
        back_populates="sala"
    )
    partidas: Mapped[list["PartidaNemPato"]] = relationship(back_populates="sala")


class ParticipanteNemPato(Base):
    __tablename__ = "participantes_nem_pato"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ATIVO', 'ABANDONOU')",
            name="ck_participantes_nem_pato_status",
        ),
        CheckConstraint(
            "ordem_entrada >= 1",
            name="ck_participantes_nem_pato_ordem_entrada_positiva",
        ),
        CheckConstraint(
            "length(trim(nome)) > 0", name="ck_participantes_nem_pato_nome_nao_vazio"
        ),
        CheckConstraint(
            "length(token_hash) = 32",
            name="ck_participantes_nem_pato_token_hash_tamanho",
        ),
        UniqueConstraint(
            "sala_id", "nome", name="uq_participantes_nem_pato_sala_nome"
        ),
        UniqueConstraint(
            "sala_id", "ordem_entrada", name="uq_participantes_nem_pato_sala_ordem"
        ),
        UniqueConstraint("token_hash", name="uq_participantes_nem_pato_token_hash"),
        Index("ix_participantes_nem_pato_sala_status", "sala_id", "status"),
        Index(
            "uq_participantes_nem_pato_anfitriao_ativo",
            "sala_id",
            unique=True,
            postgresql_where=text("eh_anfitriao IS TRUE AND status = 'ATIVO'"),
            sqlite_where=text("eh_anfitriao IS TRUE AND status = 'ATIVO'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sala_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("salas_nem_pato.id"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    ordem_entrada: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    eh_anfitriao: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    status: Mapped[ParticipanteNemPatoStatus] = mapped_column(
        _enum_string(ParticipanteNemPatoStatus, 16),
        nullable=False,
        default=ParticipanteNemPatoStatus.ATIVO,
        server_default=text("'ATIVO'"),
    )
    entrou_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    saiu_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sala: Mapped["SalaNemPato"] = relationship(back_populates="participantes")
    jogadores_partida: Mapped[list["JogadorPartidaNemPato"]] = relationship(
        back_populates="participante"
    )


class PartidaNemPato(Base):
    __tablename__ = "partidas_nem_pato"
    __table_args__ = (
        CheckConstraint(
            "status IN ('EM_ANDAMENTO', 'FINALIZADA', 'CANCELADA')",
            name="ck_partidas_nem_pato_status",
        ),
        CheckConstraint("numero >= 1", name="ck_partidas_nem_pato_numero_positivo"),
        CheckConstraint(
            "total_rodadas = 10", name="ck_partidas_nem_pato_total_rodadas_mvp"
        ),
        CheckConstraint(
            "duracao_rodada_segundos = 120",
            name="ck_partidas_nem_pato_duracao_rodada_mvp",
        ),
        CheckConstraint(
            "rodada_atual >= 0 AND rodada_atual <= total_rodadas",
            name="ck_partidas_nem_pato_rodada_atual_intervalo",
        ),
        UniqueConstraint("sala_id", "numero", name="uq_partidas_nem_pato_sala_numero"),
        Index(
            "uq_partidas_nem_pato_sala_em_andamento",
            "sala_id",
            unique=True,
            postgresql_where=text("status = 'EM_ANDAMENTO'"),
            sqlite_where=text("status = 'EM_ANDAMENTO'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sala_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("salas_nem_pato.id"), nullable=False
    )
    categoria_id: Mapped[str] = mapped_column(
        String, ForeignKey("categorias.id"), nullable=False
    )
    numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[PartidaNemPatoStatus] = mapped_column(
        _enum_string(PartidaNemPatoStatus, 20),
        nullable=False,
        default=PartidaNemPatoStatus.EM_ANDAMENTO,
        server_default=text("'EM_ANDAMENTO'"),
    )
    rodada_atual: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    total_rodadas: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=TOTAL_RODADAS_NEM_A_PATO,
        server_default=text(str(TOTAL_RODADAS_NEM_A_PATO)),
    )
    duracao_rodada_segundos: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=DURACAO_RODADA_NEM_A_PATO_SEGUNDOS,
        server_default=text(str(DURACAO_RODADA_NEM_A_PATO_SEGUNDOS)),
    )
    iniciada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finalizada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    motivo_encerramento: Mapped[str | None] = mapped_column(String(80), nullable=True)

    sala: Mapped["SalaNemPato"] = relationship(back_populates="partidas")
    categoria: Mapped["Categoria"] = relationship()
    jogadores: Mapped[list["JogadorPartidaNemPato"]] = relationship(
        back_populates="partida"
    )
    rodadas: Mapped[list["RodadaNemPato"]] = relationship(back_populates="partida")


class JogadorPartidaNemPato(Base):
    __tablename__ = "jogadores_partida_nem_pato"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ATIVO', 'ABANDONOU')",
            name="ck_jogadores_partida_nem_pato_status",
        ),
        CheckConstraint(
            "ordem_circular >= 1",
            name="ck_jogadores_partida_nem_pato_ordem_circular_positiva",
        ),
        CheckConstraint(
            "length(trim(nome_snapshot)) > 0",
            name="ck_jogadores_partida_nem_pato_nome_snapshot_nao_vazio",
        ),
        UniqueConstraint(
            "partida_id",
            "participante_id",
            name="uq_jogadores_partida_nem_pato_partida_participante",
        ),
        UniqueConstraint(
            "partida_id",
            "ordem_circular",
            name="uq_jogadores_partida_nem_pato_partida_ordem",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partida_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partidas_nem_pato.id"), nullable=False
    )
    participante_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("participantes_nem_pato.id"), nullable=False
    )
    nome_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    ordem_circular: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[ParticipanteNemPatoStatus] = mapped_column(
        _enum_string(ParticipanteNemPatoStatus, 16),
        nullable=False,
        default=ParticipanteNemPatoStatus.ATIVO,
        server_default=text("'ATIVO'"),
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    saiu_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    partida: Mapped["PartidaNemPato"] = relationship(back_populates="jogadores")
    participante: Mapped["ParticipanteNemPato"] = relationship(
        back_populates="jogadores_partida"
    )
    palpites: Mapped[list["PalpiteNemPato"]] = relationship(
        back_populates="jogador_partida"
    )


class RodadaNemPato(Base):
    __tablename__ = "rodadas_nem_pato"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AGUARDANDO_INICIO', 'EM_ANDAMENTO', 'RESULTADO')",
            name="ck_rodadas_nem_pato_status",
        ),
        CheckConstraint(
            "tipo_finalizacao IS NULL OR tipo_finalizacao IN "
            "('DESAFIO', 'TEMPO_ESGOTADO', 'SEM_PALPITE')",
            name="ck_rodadas_nem_pato_tipo_finalizacao",
        ),
        CheckConstraint(
            "numero BETWEEN 1 AND 10", name="ck_rodadas_nem_pato_numero_intervalo"
        ),
        CheckConstraint(
            "termina_em IS NULL OR iniciada_em IS NULL OR termina_em > iniciada_em",
            name="ck_rodadas_nem_pato_termina_depois_de_iniciada",
        ),
        UniqueConstraint(
            "partida_id", "numero", name="uq_rodadas_nem_pato_partida_numero"
        ),
        UniqueConstraint(
            "partida_id", "pergunta_id", name="uq_rodadas_nem_pato_partida_pergunta"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    partida_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partidas_nem_pato.id"), nullable=False
    )
    pergunta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("perguntas_nem_pato.id"), nullable=False
    )
    numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[RodadaNemPatoStatus] = mapped_column(
        _enum_string(RodadaNemPatoStatus, 24),
        nullable=False,
        default=RodadaNemPatoStatus.AGUARDANDO_INICIO,
        server_default=text("'AGUARDANDO_INICIO'"),
    )
    jogador_inicial_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jogadores_partida_nem_pato.id"), nullable=False
    )
    jogador_da_vez_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("jogadores_partida_nem_pato.id"), nullable=True
    )
    iniciada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    termina_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finalizada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tipo_finalizacao: Mapped[TipoFinalizacaoRodadaNemPato | None] = mapped_column(
        _enum_string(TipoFinalizacaoRodadaNemPato, 24), nullable=True
    )

    partida: Mapped["PartidaNemPato"] = relationship(back_populates="rodadas")
    pergunta: Mapped[PerguntaNemPato] = relationship(back_populates="rodadas")
    jogador_inicial: Mapped["JogadorPartidaNemPato"] = relationship(
        foreign_keys=[jogador_inicial_id], backref="rodadas_iniciais"
    )
    jogador_da_vez: Mapped["JogadorPartidaNemPato | None"] = relationship(
        foreign_keys=[jogador_da_vez_id], backref="rodadas_da_vez"
    )
    palpites: Mapped[list["PalpiteNemPato"]] = relationship(back_populates="rodada")


class PalpiteNemPato(Base):
    __tablename__ = "palpites_nem_pato"
    __table_args__ = (
        CheckConstraint("ordem >= 1", name="ck_palpites_nem_pato_ordem_positiva"),
        CheckConstraint("valor >= 0", name="ck_palpites_nem_pato_valor_nao_negativo"),
        UniqueConstraint(
            "rodada_id", "ordem", name="uq_palpites_nem_pato_rodada_ordem"
        ),
        UniqueConstraint(
            "rodada_id",
            "client_action_id",
            name="uq_palpites_nem_pato_rodada_client_action",
        ),
        Index("ix_palpites_nem_pato_rodada_ordem", "rodada_id", "ordem"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    rodada_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rodadas_nem_pato.id"), nullable=False
    )
    jogador_partida_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jogadores_partida_nem_pato.id"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    valor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    client_action_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)

    rodada: Mapped["RodadaNemPato"] = relationship(back_populates="palpites")
    jogador_partida: Mapped["JogadorPartidaNemPato"] = relationship(
        back_populates="palpites"
    )