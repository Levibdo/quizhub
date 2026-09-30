import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from app.db.session import get_session_factory
from app.services.categorias import (
    CategoriaDuplicada,
    CategoriaInvalida,
    categorias_service,
)
from app.services.importador_perguntas import (
    ArquivoImportacaoInvalido,
    detectar_formato,
    importador_perguntas,
)


def _listar(session, output: Callable[[str], None]) -> int:
    categorias = categorias_service.listar(session)
    if not categorias:
        output("Nenhuma categoria cadastrada.")
        return 0
    for categoria in categorias:
        descricao = categoria.descricao or "—"
        status = "ativa" if categoria.ativa else "inativa"
        output(f"{categoria.id} | {categoria.nome} | {descricao} | {status}")
    return 0


def _criar(
    session,
    input_fn: Callable[[str], str],
    output: Callable[[str], None],
) -> int:
    nome = input_fn("Nome: ")
    codigo = input_fn("Código/id: ")
    descricao = input_fn("Descrição (opcional): ")
    output("")
    output("Confira os dados:")
    output(f"Código/id: {codigo.strip()}")
    output(f"Nome: {nome.strip()}")
    output(f"Descrição: {descricao.strip() or '—'}")
    confirmacao = input_fn("Confirmar criação? [s/N]: ").strip().lower()
    if confirmacao not in {"s", "sim"}:
        output("Criação cancelada; nenhuma categoria foi alterada.")
        return 0
    try:
        categoria = categorias_service.criar(session, codigo, nome, descricao)
    except (CategoriaInvalida, CategoriaDuplicada) as erro:
        output(f"Erro: {erro}")
        return 1
    output(f"Categoria '{categoria.id}' criada com sucesso.")
    return 0


def _mostrar_relatorio(relatorio, output: Callable[[str], None]) -> None:
    output(
        f"Formato: {relatorio.formato} | Total: {relatorio.total} | "
        f"Válidas: {relatorio.validas} | Duplicadas: {relatorio.duplicadas} | "
        f"Inválidas: {relatorio.invalidas}"
    )
    for erro in relatorio.erros:
        output(f"Referência {erro.linha}: {erro.motivo}")


def _ler_arquivo(caminho: str) -> tuple[bytes, str]:
    formato = detectar_formato(caminho)
    try:
        return Path(caminho).read_bytes(), formato
    except OSError as erro:
        raise ArquivoImportacaoInvalido(
            f"não foi possível ler o arquivo: {erro}"
        ) from erro


def _validar_perguntas(
    session,
    caminho: str,
    output: Callable[[str], None],
) -> int:
    try:
        conteudo, formato = _ler_arquivo(caminho)
        relatorio = importador_perguntas.validar_arquivo(
            session, conteudo, formato
        )
    except ArquivoImportacaoInvalido as erro:
        output(f"Erro: {erro}")
        return 1
    _mostrar_relatorio(relatorio, output)
    return 0 if relatorio.invalidas == 0 else 1


def _importar_perguntas(
    session,
    caminho: str,
    input_fn: Callable[[str], str],
    output: Callable[[str], None],
) -> int:
    try:
        conteudo, formato = _ler_arquivo(caminho)
        validacao = importador_perguntas.validar_arquivo(
            session, conteudo, formato
        )
    except ArquivoImportacaoInvalido as erro:
        output(f"Erro: {erro}")
        return 1
    _mostrar_relatorio(validacao, output)
    confirmacao = input_fn("Confirmar importação? [s/N]: ").strip().lower()
    if confirmacao not in {"s", "sim"}:
        output("Importação cancelada; nenhuma pergunta foi alterada.")
        return 0
    resultado = importador_perguntas.importar_arquivo(
        session, conteudo, formato
    )
    output(
        f"Importação concluída: {resultado.criadas} criada(s), "
        f"{resultado.falhas} falha(s), {resultado.total} total."
    )
    for erro in resultado.erros:
        output(f"Referência {erro.linha}: {erro.motivo}")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
    session_factory=None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    comandos = parser.add_subparsers(dest="recurso", required=True)
    categoria = comandos.add_parser("categoria")
    acoes = categoria.add_subparsers(dest="acao", required=True)
    acoes.add_parser("listar")
    acoes.add_parser("criar")
    perguntas = comandos.add_parser("perguntas")
    acoes_perguntas = perguntas.add_subparsers(dest="acao", required=True)
    for acao in ("validar", "importar"):
        comando = acoes_perguntas.add_parser(acao)
        comando.add_argument("arquivo")
    args = parser.parse_args(argv)

    factory = session_factory or get_session_factory()
    with factory() as session:
        if args.recurso == "categoria":
            if args.acao == "listar":
                return _listar(session, output)
            return _criar(session, input_fn, output)
        if args.acao == "validar":
            return _validar_perguntas(session, args.arquivo, output)
        return _importar_perguntas(
            session, args.arquivo, input_fn, output
        )
