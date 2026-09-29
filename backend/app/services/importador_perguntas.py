from io import BytesIO
from zipfile import BadZipFile

from fastapi import HTTPException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Categoria, Pergunta
from app.schemas.perguntas import (
    ErroImportacaoPergunta,
    RelatorioImportacaoPerguntas,
)

COLUNAS_OBRIGATORIAS = (
    "categoria_id",
    "enunciado",
    "alternativa_a",
    "alternativa_b",
    "alternativa_c",
    "alternativa_d",
    "alternativa_correta",
)


def _texto_obrigatorio(valor) -> str | None:
    if valor is None:
        return None
    texto_valor = str(valor).strip()
    return texto_valor or None


def _alternativa_correta(valor) -> int | None:
    if isinstance(valor, bool):
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    if isinstance(valor, float) and not valor.is_integer():
        return None
    return numero if 0 <= numero <= 3 else None


class ImportadorPerguntas:
    def importar(
        self,
        db: Session,
        conteudo: bytes,
    ) -> RelatorioImportacaoPerguntas:
        linhas = self._ler_linhas(conteudo)
        try:
            categorias = {
                categoria.id: categoria
                for categoria in db.scalars(select(Categoria))
            }
            validadas = []
            erros = []

            for numero_linha, dados in linhas:
                validada, motivo = self._validar_linha(dados, categorias)
                if motivo is not None:
                    erros.append(
                        ErroImportacaoPergunta(
                            linha=numero_linha,
                            motivo=motivo,
                        )
                    )
                else:
                    validadas.append((numero_linha, validada))

            novas = []
            if validadas:
                if db.bind is not None and db.bind.dialect.name == "postgresql":
                    db.execute(
                        text(
                            "LOCK TABLE perguntas "
                            "IN SHARE ROW EXCLUSIVE MODE"
                        )
                    )

                # A identidade de importação é a categoria junto do enunciado,
                # ambos já normalizados com strip durante a validação. A
                # comparação permanece exata e sensível a maiúsculas/minúsculas.
                chaves_conhecidas = set(
                    db.execute(
                        select(Pergunta.categoria_id, Pergunta.enunciado)
                    ).tuples()
                )

                for numero_linha, dados in validadas:
                    chave = (dados["categoria_id"], dados["enunciado"])
                    if chave in chaves_conhecidas:
                        erros.append(
                            ErroImportacaoPergunta(
                                linha=numero_linha,
                                motivo=(
                                    "pergunta duplicada: categoria_id e enunciado "
                                    "já existentes"
                                ),
                            )
                        )
                        continue
                    chaves_conhecidas.add(chave)
                    novas.append(dados)

                proximo_id = (db.scalar(select(func.max(Pergunta.id))) or 0) + 1
                for dados in novas:
                    db.add(Pergunta(id=proximo_id, **dados))
                    proximo_id += 1

            db.flush()
            db.commit()
            return RelatorioImportacaoPerguntas(
                total=len(linhas),
                criadas=len(novas),
                falhas=len(erros),
                erros=erros,
            )
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _ler_linhas(conteudo: bytes) -> list[tuple[int, dict[str, object]]]:
        try:
            workbook = load_workbook(
                filename=BytesIO(conteudo),
                read_only=True,
                data_only=True,
            )
        except (BadZipFile, InvalidFileException, KeyError, OSError) as error:
            raise HTTPException(status_code=422, detail="arquivo XLSX inválido") from error

        try:
            worksheet = workbook.active
            iterator = worksheet.iter_rows(values_only=True)
            cabecalho_original = next(iterator, None)
            if cabecalho_original is None:
                raise HTTPException(
                    status_code=422,
                    detail="arquivo sem cabeçalho",
                )

            cabecalho = [
                str(valor).strip() if valor is not None else ""
                for valor in cabecalho_original
            ]
            ausentes = [
                coluna for coluna in COLUNAS_OBRIGATORIAS if coluna not in cabecalho
            ]
            if ausentes:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "colunas obrigatórias ausentes: " + ", ".join(ausentes)
                    ),
                )

            indices = {
                coluna: cabecalho.index(coluna) for coluna in COLUNAS_OBRIGATORIAS
            }
            linhas = []
            for numero_linha, valores in enumerate(iterator, start=2):
                dados = {
                    coluna: valores[indice] if indice < len(valores) else None
                    for coluna, indice in indices.items()
                }
                linhas.append((numero_linha, dados))
            return linhas
        finally:
            workbook.close()

    @staticmethod
    def _validar_linha(
        dados: dict[str, object],
        categorias: dict[str, Categoria],
    ) -> tuple[dict[str, object] | None, str | None]:
        textos = {
            coluna: _texto_obrigatorio(dados[coluna])
            for coluna in COLUNAS_OBRIGATORIAS
            if coluna != "alternativa_correta"
        }
        for coluna, valor in textos.items():
            if valor is None:
                return None, f"campo obrigatório vazio: {coluna}"

        if dados["alternativa_correta"] is None or str(
            dados["alternativa_correta"]
        ).strip() == "":
            return None, "campo obrigatório vazio: alternativa_correta"

        alternativa = _alternativa_correta(dados["alternativa_correta"])
        if alternativa is None:
            return None, "alternativa_correta deve estar entre 0 e 3"

        categoria = categorias.get(textos["categoria_id"])
        if categoria is None:
            return None, "categoria inexistente"
        if not categoria.ativa:
            return None, "categoria inativa"

        return {
            **textos,
            "alternativa_correta": alternativa,
            "ativa": True,
        }, None


importador_perguntas = ImportadorPerguntas()
