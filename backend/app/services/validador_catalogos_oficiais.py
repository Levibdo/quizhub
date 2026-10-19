import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl, BaseModel, ConfigDict, Field, StrictInt, ValidationError,
)


SCHEMA_QUIZ = "quizhub.quiz_classico.v2"
SCHEMA_NEM_PATO = "quizhub.nem_a_pato.macabro.v1"
SCHEMA_MANIFESTO = "quizhub.catalogos.manifest.v1"
CATEGORIAS_QUIZ = ("geral", "tecnologia", "matematica", "entretenimento")
DISTRIBUICAO_QUIZ = {"FACIL": 30, "MEDIA": 45, "DIFICIL": 25}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_EDITORIAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")


class ContratoBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FonteEditorial(ContratoBase):
    titulo: str = Field(min_length=1, max_length=300)
    url: AnyHttpUrl
    acessada_em: date


class PerguntaQuizEditorial(ContratoBase):
    id_editorial: str = Field(pattern=ID_EDITORIAL_RE.pattern)
    enunciado: str = Field(min_length=1)
    dificuldade: Literal["FACIL", "MEDIA", "DIFICIL"]
    alternativas: list[str] = Field(min_length=4, max_length=4)
    resposta_correta: StrictInt = Field(ge=0, le=3)
    explicacao: str = Field(min_length=1)
    fontes: list[FonteEditorial] = Field(min_length=1)


class CategoriaQuizEditorial(ContratoBase):
    slug: Literal["geral", "tecnologia", "matematica", "entretenimento"]
    nome: str = Field(min_length=1, max_length=100)
    perguntas: list[PerguntaQuizEditorial]


class CatalogoQuizEditorial(ContratoBase):
    schema_version: Literal["quizhub.quiz_classico.v2"]
    catalogo_id: str = Field(pattern=ID_EDITORIAL_RE.pattern)
    versao: StrictInt = Field(ge=1)
    modo: Literal["QUIZ_CLASSICO"]
    categorias: list[CategoriaQuizEditorial]


class PerguntaNemPatoEditorial(ContratoBase):
    id_editorial: str = Field(pattern=ID_EDITORIAL_RE.pattern)
    enunciado: str = Field(min_length=1)
    resposta_numerica: StrictInt = Field(ge=0, le=9223372036854775807)
    unidade: str = Field(min_length=1, max_length=100)
    explicacao: str = Field(min_length=1)
    tema_editorial: str = Field(min_length=1, max_length=100)
    natureza_resposta: Literal["EXATA", "ESTIMATIVA"]
    qualificacao_estimativa: str | None = Field(default=None, min_length=1)
    fontes: list[FonteEditorial] = Field(min_length=1)


class CategoriaNemPatoEditorial(ContratoBase):
    slug: Literal["macabro"]
    nome: str = Field(min_length=1, max_length=100)
    perguntas: list[PerguntaNemPatoEditorial]


class CatalogoNemPatoEditorial(ContratoBase):
    schema_version: Literal["quizhub.nem_a_pato.macabro.v1"]
    catalogo_id: str = Field(pattern=ID_EDITORIAL_RE.pattern)
    versao: StrictInt = Field(ge=1)
    modo: Literal["NEM_A_PATO"]
    categoria: CategoriaNemPatoEditorial


class ItemManifesto(ContratoBase):
    catalogo_id: str = Field(pattern=ID_EDITORIAL_RE.pattern)
    arquivo: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    sha256: str | None = None
    status: Literal["PENDENTE", "PRONTO"]


class ManifestoCatalogos(ContratoBase):
    schema_version: Literal["quizhub.catalogos.manifest.v1"]
    catalogos: list[ItemManifesto]


@dataclass(frozen=True)
class OcorrenciaValidacao:
    nivel: Literal["ERRO", "AVISO"]
    codigo: str
    mensagem: str
    referencia: str | None = None


@dataclass
class RelatorioCatalogos:
    ocorrencias: list[OcorrenciaValidacao] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)

    @property
    def erros(self) -> list[OcorrenciaValidacao]:
        return [item for item in self.ocorrencias if item.nivel == "ERRO"]

    @property
    def avisos(self) -> list[OcorrenciaValidacao]:
        return [item for item in self.ocorrencias if item.nivel == "AVISO"]

    @property
    def valido(self) -> bool:
        return not self.erros

    def adicionar(
        self, nivel: Literal["ERRO", "AVISO"], codigo: str, mensagem: str,
        referencia: str | None = None,
    ) -> None:
        self.ocorrencias.append(OcorrenciaValidacao(
            nivel=nivel, codigo=codigo, mensagem=mensagem, referencia=referencia
        ))


def sha256_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _normalizar(texto: str) -> str:
    sem_acentos = "".join(
        caractere for caractere in unicodedata.normalize("NFKD", texto.casefold())
        if not unicodedata.combining(caractere)
    )
    return " ".join(re.findall(r"[a-z0-9]+", sem_acentos))


def _normalizar_alternativa(texto: str) -> str:
    # Aqui operadores são conteúdo: -3/3, ==/equals e <=/< não podem colapsar.
    normalizado = unicodedata.normalize("NFKC", texto).casefold().strip()
    normalizado = normalizado.replace("−", "-").replace("–", "-")
    return " ".join(normalizado.split())


def _carregar(caminho: Path, modelo, relatorio: RelatorioCatalogos):
    try:
        bruto = caminho.read_bytes()
        documento = json.loads(bruto.decode("utf-8"))
    except OSError as erro:
        relatorio.adicionar("ERRO", "arquivo_inacessivel", str(erro), str(caminho))
        return None
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        relatorio.adicionar(
            "ERRO", "json_invalido", f"JSON inválido ou fora de UTF-8: {erro}",
            str(caminho),
        )
        return None
    relatorio.hashes[str(caminho)] = hashlib.sha256(bruto).hexdigest()
    try:
        return modelo.model_validate(documento)
    except ValidationError as erro:
        for detalhe in erro.errors(include_url=False):
            local = ".".join(str(parte) for parte in detalhe["loc"])
            relatorio.adicionar(
                "ERRO", "contrato_invalido", detalhe["msg"],
                f"{caminho}:{local}",
            )
        return None


def _validar_textos(
    perguntas: list, relatorio: RelatorioCatalogos, prefixo: str
) -> None:
    ids = Counter(item.id_editorial for item in perguntas)
    for editorial_id, total in ids.items():
        if total > 1:
            relatorio.adicionar(
                "ERRO", "id_editorial_duplicado",
                f"ID editorial repetido {total} vezes", editorial_id,
            )
    normalizados: dict[str, list[str]] = {}
    for item in perguntas:
        normalizados.setdefault(_normalizar(item.enunciado), []).append(
            item.id_editorial
        )
    for texto, editoriais in normalizados.items():
        if texto and len(editoriais) > 1:
            relatorio.adicionar(
                "ERRO", "enunciado_duplicado",
                f"enunciado normalizado repetido: {', '.join(editoriais)}", prefixo,
            )
    unicos = [(item.id_editorial, _normalizar(item.enunciado)) for item in perguntas]
    for indice, (id_a, texto_a) in enumerate(unicos):
        tokens_a = set(texto_a.split())
        for id_b, texto_b in unicos[indice + 1:]:
            if texto_a == texto_b:
                continue
            tokens_b = set(texto_b.split())
            jaccard = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
            sequencia = (
                SequenceMatcher(None, texto_a, texto_b).ratio()
                if jaccard >= 0.5 else 0.0
            )
            if max(jaccard, sequencia) >= 0.86:
                relatorio.adicionar(
                    "AVISO", "similaridade_semantica",
                    f"revisão humana recomendada ({max(jaccard, sequencia):.2f}): "
                    f"{id_a} e {id_b}", prefixo,
                )


def validar_quiz(caminho: Path, relatorio: RelatorioCatalogos) -> None:
    catalogo = _carregar(caminho, CatalogoQuizEditorial, relatorio)
    if catalogo is None:
        return
    slugs = [categoria.slug for categoria in catalogo.categorias]
    if sorted(slugs) != sorted(CATEGORIAS_QUIZ) or len(slugs) != len(set(slugs)):
        relatorio.adicionar(
            "ERRO", "categorias_invalidas",
            "o catálogo deve conter exatamente as quatro categorias oficiais",
            str(caminho),
        )
    todas = []
    for categoria in catalogo.categorias:
        todas.extend(categoria.perguntas)
        if len(categoria.perguntas) != 100:
            relatorio.adicionar(
                "ERRO", "contagem_incorreta",
                f"{categoria.slug} possui {len(categoria.perguntas)}; esperado 100",
                categoria.slug,
            )
        distribuicao = Counter(item.dificuldade for item in categoria.perguntas)
        if dict(distribuicao) != DISTRIBUICAO_QUIZ:
            relatorio.adicionar(
                "ERRO", "distribuicao_incorreta",
                f"distribuição {dict(distribuicao)}; esperada {DISTRIBUICAO_QUIZ}",
                categoria.slug,
            )
        for pergunta in categoria.perguntas:
            alternativas = [
                _normalizar_alternativa(item) for item in pergunta.alternativas
            ]
            if any(not item for item in alternativas) or len(set(alternativas)) != 4:
                relatorio.adicionar(
                    "ERRO", "alternativas_invalidas",
                    "as quatro alternativas devem ser distintas e não vazias",
                    pergunta.id_editorial,
                )
    _validar_textos(todas, relatorio, "quiz_classico")


def validar_nem_pato(caminho: Path, relatorio: RelatorioCatalogos) -> None:
    catalogo = _carregar(caminho, CatalogoNemPatoEditorial, relatorio)
    if catalogo is None:
        return
    perguntas = catalogo.categoria.perguntas
    if len(perguntas) != 100:
        relatorio.adicionar(
            "ERRO", "contagem_incorreta",
            f"macabro possui {len(perguntas)}; esperado 100", "macabro",
        )
    for pergunta in perguntas:
        if (
            pergunta.natureza_resposta == "ESTIMATIVA"
            and not (pergunta.qualificacao_estimativa or "").strip()
        ):
            relatorio.adicionar(
                "ERRO", "estimativa_sem_qualificacao",
                "estimativas históricas devem explicar período, método ou incerteza",
                pergunta.id_editorial,
            )
        if pergunta.natureza_resposta == "EXATA" and pergunta.qualificacao_estimativa:
            relatorio.adicionar(
                "AVISO", "qualificacao_desnecessaria",
                "resposta EXATA possui qualificação de estimativa",
                pergunta.id_editorial,
            )
    _validar_textos(perguntas, relatorio, "nem_a_pato:macabro")


def validar_manifesto(
    caminho: Path, relatorio: RelatorioCatalogos, base: Path | None = None
) -> None:
    manifesto = _carregar(caminho, ManifestoCatalogos, relatorio)
    if manifesto is None:
        return
    esperados = {
        "quiz_classico_v2": ("quiz_classico_v2.json", SCHEMA_QUIZ),
        "nem_a_pato_macabro_v1": ("nem_a_pato_macabro_v1.json", SCHEMA_NEM_PATO),
    }
    itens = {item.catalogo_id: item for item in manifesto.catalogos}
    if set(itens) != set(esperados) or len(manifesto.catalogos) != len(itens):
        relatorio.adicionar(
            "ERRO", "manifesto_incompleto",
            "manifesto deve declarar exatamente os dois catálogos oficiais",
            str(caminho),
        )
        return
    raiz = base or caminho.parent
    for catalogo_id, (arquivo, schema) in esperados.items():
        item = itens[catalogo_id]
        if item.arquivo != arquivo or item.schema_version != schema:
            relatorio.adicionar(
                "ERRO", "manifesto_contrato_incorreto",
                f"metadados incorretos para {catalogo_id}", catalogo_id,
            )
        alvo = raiz / item.arquivo
        if item.status == "PENDENTE":
            if item.sha256 is not None:
                relatorio.adicionar(
                    "ERRO", "manifesto_hash_pendente",
                    "catálogo pendente não deve declarar hash", catalogo_id,
                )
            continue
        if item.sha256 is None or not SHA256_RE.fullmatch(item.sha256):
            relatorio.adicionar(
                "ERRO", "manifesto_hash_invalido", "SHA-256 ausente ou inválido",
                catalogo_id,
            )
        elif not alvo.is_file():
            relatorio.adicionar(
                "ERRO", "manifesto_arquivo_ausente", "arquivo pronto não encontrado",
                str(alvo),
            )
        elif sha256_arquivo(alvo) != item.sha256:
            relatorio.adicionar(
                "ERRO", "manifesto_hash_divergente", "SHA-256 não confere",
                str(alvo),
            )


def validar_catalogos(
    *, quiz: Path | None = None, nem_pato: Path | None = None,
    manifesto: Path | None = None,
) -> RelatorioCatalogos:
    relatorio = RelatorioCatalogos()
    if quiz is not None:
        validar_quiz(quiz, relatorio)
    if nem_pato is not None:
        validar_nem_pato(nem_pato, relatorio)
    if manifesto is not None:
        validar_manifesto(manifesto, relatorio)
    if quiz is None and nem_pato is None and manifesto is None:
        relatorio.adicionar(
            "ERRO", "nenhum_arquivo", "informe ao menos um arquivo para validação"
        )
    return relatorio
