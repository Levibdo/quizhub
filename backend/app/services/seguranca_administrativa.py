import json
import os
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


LEGACY_ADMIN_IMPORT_ENABLED_ENV = "LEGACY_ADMIN_IMPORT_ENABLED"
LEGACY_ADMIN_IMPORT_MAX_BYTES_ENV = "LEGACY_ADMIN_IMPORT_MAX_BYTES"
LEGACY_ADMIN_IMPORT_MAX_BYTES_DEFAULT = 5 * 1024 * 1024

CHAVES_SENSIVEIS = (
    "authorization",
    "cookie",
    "credencial",
    "password",
    "senha",
    "secret",
    "segredo",
    "token",
)
MAX_PROFUNDIDADE_DETALHES = 4
MAX_ITENS_DETALHES = 50
MAX_TEXTO_DETALHES = 500
MAX_BYTES_DETALHES = 8 * 1024


class ArquivoAdministrativoMuitoGrande(ValueError):
    pass


def importacao_legada_habilitada() -> bool:
    return os.getenv(LEGACY_ADMIN_IMPORT_ENABLED_ENV, "true").strip().lower() in {
        "1", "true", "yes", "on",
    }


def limite_importacao_legada() -> int:
    bruto = os.getenv(
        LEGACY_ADMIN_IMPORT_MAX_BYTES_ENV,
        str(LEGACY_ADMIN_IMPORT_MAX_BYTES_DEFAULT),
    ).strip()
    try:
        limite = int(bruto)
    except ValueError as erro:
        raise RuntimeError(
            f"{LEGACY_ADMIN_IMPORT_MAX_BYTES_ENV} deve ser um inteiro positivo"
        ) from erro
    if limite < 1:
        raise RuntimeError(
            f"{LEGACY_ADMIN_IMPORT_MAX_BYTES_ENV} deve ser um inteiro positivo"
        )
    return limite


def ler_upload_limitado(arquivo, limite: int) -> bytes:
    conteudo = arquivo.read(limite + 1)
    if len(conteudo) > limite:
        raise ArquivoAdministrativoMuitoGrande(
            f"arquivo excede o limite de {limite} bytes"
        )
    return conteudo


def _normalizar_chave(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor)).encode(
        "ascii", "ignore"
    ).decode("ascii")
    return texto.casefold().replace("-", "_")


def _chave_sensivel(chave: object) -> bool:
    normalizada = _normalizar_chave(chave)
    return any(item in normalizada for item in CHAVES_SENSIVEIS)


def _sanitizar(valor: Any, profundidade: int) -> Any:
    if profundidade > MAX_PROFUNDIDADE_DETALHES:
        return "[LIMITE_DE_PROFUNDIDADE]"
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    if isinstance(valor, str):
        return valor[:MAX_TEXTO_DETALHES]
    if isinstance(valor, Mapping):
        saida = {}
        for indice, (chave, item) in enumerate(valor.items()):
            if indice >= MAX_ITENS_DETALHES:
                saida["_truncado"] = True
                break
            chave_texto = str(chave)[:100]
            saida[chave_texto] = (
                "[REMOVIDO]" if _chave_sensivel(chave)
                else _sanitizar(item, profundidade + 1)
            )
        return saida
    if isinstance(valor, Sequence) and not isinstance(
        valor, (bytes, bytearray, memoryview)
    ):
        itens = list(valor)
        saida = [
            _sanitizar(item, profundidade + 1)
            for item in itens[:MAX_ITENS_DETALHES]
        ]
        if len(itens) > MAX_ITENS_DETALHES:
            saida.append("[TRUNCADO]")
        return saida
    return str(valor)[:MAX_TEXTO_DETALHES]


def sanitizar_detalhes_auditoria(
    detalhes: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if detalhes is None:
        return None
    sanitizados = _sanitizar(detalhes, 0)
    serializados = json.dumps(
        sanitizados, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")
    if len(serializados) <= MAX_BYTES_DETALHES:
        return sanitizados
    return {
        "truncado": True,
        "motivo": "DETALHES_EXCEDEM_LIMITE",
        "tamanho_original": len(serializados),
    }
