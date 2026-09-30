import argparse
from collections.abc import Callable, Sequence

from app.db.session import get_session_factory
from app.services.categorias import (
    CategoriaDuplicada,
    CategoriaInvalida,
    categorias_service,
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
    args = parser.parse_args(argv)

    factory = session_factory or get_session_factory()
    with factory() as session:
        if args.acao == "listar":
            return _listar(session, output)
        return _criar(session, input_fn, output)
