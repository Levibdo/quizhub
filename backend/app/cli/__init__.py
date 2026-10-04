import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from app.db.session import get_session_factory
from app.services.categorias import (
    CategoriaDuplicada,
    CategoriaInvalida,
    categorias_service,
)
from app.services.catalogo_nem_a_pato import (
    ArquivoCatalogoNemAPatoInvalido,
    CatalogoNemAPatoInvalido,
    catalogo_perguntas_nem_a_pato,
    detectar_formato_catalogo,
)
from app.services.importador_perguntas import (
    ArquivoImportacaoInvalido,
    detectar_formato,
    importador_perguntas,
)
from app.services.gerador_prompt import (
    DIFICULDADES,
    PUBLICO_PADRAO,
    ParametrosPrompt,
    ParametrosPromptInvalidos,
    gerar_prompt_perguntas,
)


def _listar(session, output: Callable[[str], None]) -> int:
    categorias = categorias_service.listar(session)
    if not categorias:
        output("Nenhuma categoria cadastrada.")
        return 0
    for categoria in categorias:
        descricao = categoria.descricao or "—"
        status = "ativa" if categoria.ativa else "inativa"
        output(f"{categoria.slug} | {categoria.nome} | {descricao} | {status}")
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
    output(f"Categoria '{categoria.slug}' criada com sucesso.")
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


def _gerar_prompt(
    session,
    input_fn: Callable[[str], str],
    output: Callable[[str], None],
) -> int:
    categorias = categorias_service.listar(session, somente_ativas=True)
    if not categorias:
        output("Erro: nenhuma categoria ativa disponível.")
        return 1

    output("Categorias ativas:")
    for indice, categoria in enumerate(categorias, start=1):
        output(f"{indice}. {categoria.nome} ({categoria.slug})")

    escolha_categoria = input_fn("Categoria (número ou id): ").strip()
    categoria = next(
        (
            item
            for indice, item in enumerate(categorias, start=1)
            if escolha_categoria in {str(indice), item.slug}
        ),
        None,
    )
    if categoria is None:
        output("Erro: selecione uma categoria ativa existente.")
        return 1

    tema = input_fn("Tema: ")
    quantidade_texto = input_fn("Quantidade de perguntas: ").strip()
    try:
        quantidade = int(quantidade_texto)
    except ValueError:
        output("Erro: quantidade deve ser um número inteiro.")
        return 1

    output("Dificuldades:")
    for indice, dificuldade in enumerate(DIFICULDADES, start=1):
        output(f"{indice}. {dificuldade}")
    escolha_dificuldade = input_fn("Dificuldade: ").strip()
    dificuldade = next(
        (
            item
            for indice, item in enumerate(DIFICULDADES, start=1)
            if escolha_dificuldade.casefold()
            in {str(indice), item.casefold()}
        ),
        escolha_dificuldade,
    )
    publico_alvo = input_fn(
        f"Público-alvo [{PUBLICO_PADRAO}]: "
    )

    try:
        prompt = gerar_prompt_perguntas(
            ParametrosPrompt(
                categoria_id=categoria.slug,
                tema=tema,
                quantidade=quantidade,
                dificuldade=dificuldade,
                publico_alvo=publico_alvo,
            )
        )
    except ParametrosPromptInvalidos as erro:
        output(f"Erro: {erro}")
        return 1

    output("")
    output("----- PROMPT GERADO -----")
    output(prompt)
    output("----- FIM DO PROMPT -----")
    return 0


def _ler_arquivo_nem_a_pato(caminho: str) -> tuple[bytes, str]:
    formato = detectar_formato_catalogo(caminho)
    try:
        return Path(caminho).read_bytes(), formato
    except OSError as erro:
        raise ArquivoCatalogoNemAPatoInvalido(
            f"não foi possível ler o arquivo: {erro}"
        ) from erro


def _mostrar_validacao_nem_a_pato(relatorio, output: Callable[[str], None]) -> None:
    output(
        f"Formato: {relatorio.formato} | Total: {relatorio.total} | "
        f"Válidas: {len(relatorio.validas)} | Duplicadas: {relatorio.duplicadas} | "
        f"Inválidas: {relatorio.invalidas}"
    )
    for erro in relatorio.erros:
        output(f"Referência {erro.referencia}: {erro.motivo}")


def _validar_nem_a_pato(
    session, caminho: str, output: Callable[[str], None]
) -> int:
    try:
        conteudo, formato = _ler_arquivo_nem_a_pato(caminho)
        relatorio = catalogo_perguntas_nem_a_pato.validar_arquivo(
            session, conteudo, formato
        )
    except ArquivoCatalogoNemAPatoInvalido as erro:
        output(f"Erro: {erro}")
        return 1
    _mostrar_validacao_nem_a_pato(relatorio, output)
    return 0 if relatorio.invalidas == 0 else 1


def _importar_nem_a_pato(
    session,
    caminho: str,
    input_fn: Callable[[str], str],
    output: Callable[[str], None],
) -> int:
    try:
        conteudo, formato = _ler_arquivo_nem_a_pato(caminho)
        validacao = catalogo_perguntas_nem_a_pato.validar_arquivo(
            session, conteudo, formato
        )
    except ArquivoCatalogoNemAPatoInvalido as erro:
        output(f"Erro: {erro}")
        return 1
    _mostrar_validacao_nem_a_pato(validacao, output)
    if validacao.invalidas:
        output("Importação cancelada; há registros inválidos e nenhum foi importado.")
        return 1
    confirmacao = input_fn("Confirmar importação? [s/N]: ").strip().casefold()
    if confirmacao not in {"s", "sim"}:
        output("Importação cancelada; nenhuma pergunta foi alterada.")
        return 0
    try:
        resultado = catalogo_perguntas_nem_a_pato.importar_arquivo(
            session, conteudo, formato
        )
    except CatalogoNemAPatoInvalido as erro:
        _mostrar_validacao_nem_a_pato(erro.relatorio, output)
        output("Importação cancelada; nenhum registro foi importado.")
        return 1
    output(
        f"Importação concluída: {resultado.criadas} criada(s), "
        f"{resultado.duplicadas} duplicada(s), {resultado.falhas} falha(s)."
    )
    return 0


def _listar_nem_a_pato(session, output: Callable[[str], None]) -> int:
    perguntas = catalogo_perguntas_nem_a_pato.listar(session)
    if not perguntas:
        output("Nenhuma pergunta Nem a Pato cadastrada.")
        return 0
    output("ID | Categoria | Enunciado | Unidade | Ativa")
    for pergunta_id, categoria, enunciado, unidade, ativa in perguntas:
        output(
            f"{pergunta_id} | {categoria} | {enunciado} | "
            f"{unidade or '—'} | {'sim' if ativa else 'não'}"
        )
    return 0


def _resumo_nem_a_pato(session, output: Callable[[str], None]) -> int:
    resumo = catalogo_perguntas_nem_a_pato.resumo(session)
    output(
        f"Total: {resumo['total']} | Ativas: {resumo['ativas']} | "
        f"Inativas: {resumo['inativas']}"
    )
    for categoria, quantidade in resumo["por_categoria"]:
        output(f"{categoria}: {quantidade}")
    return 0


def _criar_pergunta_nem_a_pato(
    session,
    input_fn: Callable[[str], str],
    output: Callable[[str], None],
) -> int:
    dados = {
        "categoria_id": input_fn("Categoria (id): "),
        "enunciado": input_fn("Enunciado: "),
        "resposta_numerica": input_fn("Resposta numérica (inteiro >= 0): "),
        "unidade": input_fn("Unidade (opcional): "),
        "explicacao": input_fn("Explicação: "),
        "fonte": input_fn("Fonte (opcional): "),
        "ativa": input_fn("Ativa? [S/n]: ") or None,
    }
    try:
        pergunta = catalogo_perguntas_nem_a_pato.criar(session, dados)
    except ValueError as erro:
        output(f"Erro: {erro}")
        return 1
    output(f"Pergunta Nem a Pato {pergunta.id} criada com sucesso.")
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
    prompt = comandos.add_parser("prompt")
    acoes_prompt = prompt.add_subparsers(dest="acao", required=True)
    acoes_prompt.add_parser("gerar")
    nem_pato = comandos.add_parser("nem-pato")
    recursos_nem_pato = nem_pato.add_subparsers(dest="recurso_nem_pato", required=True)
    perguntas_nem_pato = recursos_nem_pato.add_parser("perguntas")
    acoes_nem_pato = perguntas_nem_pato.add_subparsers(
        dest="acao_nem_pato", required=True
    )
    for acao in ("validar", "importar"):
        comando = acoes_nem_pato.add_parser(acao)
        comando.add_argument("arquivo")
    for acao in ("listar", "resumo", "criar"):
        acoes_nem_pato.add_parser(acao)
    args = parser.parse_args(argv)

    factory = session_factory or get_session_factory()
    with factory() as session:
        if args.recurso == "categoria":
            if args.acao == "listar":
                return _listar(session, output)
            return _criar(session, input_fn, output)
        if args.recurso == "prompt":
            return _gerar_prompt(session, input_fn, output)
        if args.recurso == "nem-pato":
            if args.acao_nem_pato == "validar":
                return _validar_nem_a_pato(session, args.arquivo, output)
            if args.acao_nem_pato == "importar":
                return _importar_nem_a_pato(
                    session, args.arquivo, input_fn, output
                )
            if args.acao_nem_pato == "listar":
                return _listar_nem_a_pato(session, output)
            if args.acao_nem_pato == "resumo":
                return _resumo_nem_a_pato(session, output)
            return _criar_pergunta_nem_a_pato(session, input_fn, output)
        if args.acao == "validar":
            return _validar_perguntas(session, args.arquivo, output)
        return _importar_perguntas(
            session, args.arquivo, input_fn, output
        )
