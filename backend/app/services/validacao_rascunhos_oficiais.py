import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CatalogoOficial, CatalogoOficialRascunho, Categoria,
    PerguntaNemPatoRascunho, PerguntaQuizRascunho,
)

BIGINT_MAX = 2**63 - 1
ID_EDITORIAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
TIPOS_ALTERACAO = {"INALTERADA", "MODIFICADA", "ADICIONADA", "REMOVIDA"}


def _texto(valor):
    return (valor or "").strip()


def _normalizar(texto):
    sem_acentos = "".join(
        caractere for caractere in unicodedata.normalize("NFKD", _texto(texto).casefold())
        if not unicodedata.combining(caractere)
    )
    return " ".join(re.findall(r"[a-z0-9]+", sem_acentos))


def _normalizar_alternativa(texto):
    normalizado = unicodedata.normalize("NFKC", _texto(texto)).casefold()
    return " ".join(normalizado.replace("−", "-").replace("–", "-").split())


def _url_http_valida(valor):
    try:
        url = urlparse(_texto(valor))
        return url.scheme in {"http", "https"} and bool(url.netloc) and not url.username
    except (TypeError, ValueError):
        return False


def _achado(codigo, nivel, mensagem, *, pergunta=None, campo=None, recomendacao=None):
    return {
        "codigo": codigo, "nivel": nivel,
        "pergunta_id": getattr(pergunta, "id", None),
        "id_editorial": getattr(pergunta, "id_editorial", None),
        "campo": campo, "mensagem": mensagem, "recomendacao": recomendacao,
    }


def _validar_fontes(pergunta, achados):
    fontes = list(getattr(pergunta, "fontes", []) or [])
    if not fontes:
        achados.append(_achado(
            "FONTE_OBRIGATORIA_AUSENTE", "ERRO",
            "A pergunta não possui referência editorial estruturada.", pergunta=pergunta,
            campo="referencias", recomendacao="Adicionar ao menos uma referência editorial.",
        ))
        return
    ordens = [fonte.ordem for fonte in fontes]
    if len(ordens) != len(set(ordens)) or sorted(ordens) != list(range(1, len(fontes) + 1)):
        achados.append(_achado(
            "ORDEM_REFERENCIAS_INVALIDA", "ERRO",
            "As referências devem ter ordens únicas e consecutivas a partir de 1.",
            pergunta=pergunta, campo="referencias",
            recomendacao="Reordenar as referências sem lacunas ou repetições.",
        ))
    for fonte in fontes:
        if not _texto(fonte.titulo) or fonte.acessada_em is None:
            achados.append(_achado(
                "FONTE_METADADOS_INCOMPLETOS", "AVISO",
                "Uma referência possui metadados editoriais incompletos.", pergunta=pergunta,
                campo="referencias", recomendacao="Revisar título e data de acesso da referência.",
            ))
        if not _url_http_valida(fonte.url):
            achados.append(_achado(
                "URL_FONTE_INVALIDA", "ERRO", "Uma referência não possui URL HTTP(S) válida.",
                pergunta=pergunta, campo="referencias",
                recomendacao="Informar uma URL HTTP ou HTTPS estruturalmente válida.",
            ))


def _validar_comum(pergunta, categoria, modo, achados):
    if not _texto(pergunta.id_editorial) or not ID_EDITORIAL_RE.fullmatch(_texto(pergunta.id_editorial)):
        achados.append(_achado("ID_EDITORIAL_INVALIDO", "ERRO", "O ID editorial é ausente ou inválido.", pergunta=pergunta, campo="id_editorial", recomendacao="Usar de 3 a 80 caracteres alfanuméricos, ponto, hífen ou sublinhado."))
    if not _texto(pergunta.enunciado):
        achados.append(_achado("ENUNCIADO_OBRIGATORIO", "ERRO", "O enunciado é obrigatório.", pergunta=pergunta, campo="enunciado", recomendacao="Preencher o enunciado."))
    if not _texto(pergunta.explicacao):
        achados.append(_achado("EXPLICACAO_OBRIGATORIA", "ERRO", "A explicação é obrigatória.", pergunta=pergunta, campo="explicacao", recomendacao="Adicionar uma explicação editorial."))
    elif len(_texto(pergunta.explicacao)) < 40:
        achados.append(_achado("EXPLICACAO_CURTA", "AVISO", "A explicação é curta e deve ser revisada editorialmente.", pergunta=pergunta, campo="explicacao", recomendacao="Complementar a justificativa sem alterar fatos sem evidência."))
    if categoria is None or categoria.origem != "OFICIAL" or categoria.modo != modo:
        achados.append(_achado("CATEGORIA_OFICIAL_INCOMPATIVEL", "ERRO", "A categoria não existe ou não é oficial e compatível com o modo.", pergunta=pergunta, campo="categoria_id", recomendacao="Selecionar uma categoria oficial do mesmo modo."))
    elif pergunta.categoria_slug_snapshot != categoria.slug or pergunta.categoria_nome_snapshot != categoria.nome:
        achados.append(_achado("SNAPSHOT_CATEGORIA_DIVERGENTE", "AVISO", "O nome ou slug preservado da categoria diverge do cadastro atual.", pergunta=pergunta, campo="categoria_id", recomendacao="Revisar conscientemente o vínculo antes de publicar."))
    if pergunta.tipo_alteracao not in TIPOS_ALTERACAO:
        achados.append(_achado("ESTADO_PERGUNTA_INVALIDO", "ERRO", "O estado editorial da pergunta é inválido.", pergunta=pergunta, campo="tipo_alteracao"))
    _validar_fontes(pergunta, achados)


def _validar_quiz(pergunta, categoria, achados):
    _validar_comum(pergunta, categoria, "QUIZ_CLASSICO", achados)
    alternativas = [pergunta.alternativa_a, pergunta.alternativa_b, pergunta.alternativa_c, pergunta.alternativa_d]
    normalizadas = [_normalizar_alternativa(item) for item in alternativas]
    if any(not item for item in normalizadas):
        achados.append(_achado("ALTERNATIVA_VAZIA", "ERRO", "As quatro alternativas devem ser preenchidas.", pergunta=pergunta, campo="alternativas", recomendacao="Preencher todas as alternativas."))
    if len(set(normalizadas)) != 4:
        achados.append(_achado("ALTERNATIVAS_EQUIVALENTES", "ERRO", "As alternativas devem ser distintas após normalização.", pergunta=pergunta, campo="alternativas", recomendacao="Substituir alternativas repetidas ou equivalentes."))
    if pergunta.alternativa_correta not in range(4):
        achados.append(_achado("GABARITO_INVALIDO", "ERRO", "O índice do gabarito deve estar entre 0 e 3.", pergunta=pergunta, campo="alternativa_correta", recomendacao="Selecionar uma das quatro alternativas."))
    if pergunta.dificuldade not in {"FACIL", "MEDIA", "DIFICIL"}:
        achados.append(_achado("DIFICULDADE_INVALIDA", "ERRO", "A dificuldade informada não é suportada.", pergunta=pergunta, campo="dificuldade"))


def _validar_nem_pato(pergunta, categoria, achados):
    _validar_comum(pergunta, categoria, "NEM_A_PATO", achados)
    if not isinstance(pergunta.resposta_numerica, int) or isinstance(pergunta.resposta_numerica, bool) or not 0 <= pergunta.resposta_numerica <= BIGINT_MAX:
        achados.append(_achado("RESPOSTA_NUMERICA_INVALIDA", "ERRO", "A resposta deve ser um inteiro não negativo compatível com BIGINT.", pergunta=pergunta, campo="resposta_numerica", recomendacao=f"Usar um inteiro entre 0 e {BIGINT_MAX}."))
    if not _texto(pergunta.unidade):
        achados.append(_achado("UNIDADE_OBRIGATORIA", "ERRO", "A unidade da resposta é obrigatória.", pergunta=pergunta, campo="unidade", recomendacao="Informar a unidade ou grandeza estimada."))
    if pergunta.natureza_resposta not in {"EXATA", "ESTIMATIVA"}:
        achados.append(_achado("NATUREZA_RESPOSTA_INVALIDA", "ERRO", "A natureza da resposta é inválida.", pergunta=pergunta, campo="natureza_resposta"))
    elif pergunta.natureza_resposta == "ESTIMATIVA" and not _texto(pergunta.qualificacao_estimativa):
        achados.append(_achado("ESTIMATIVA_SEM_QUALIFICACAO", "ERRO", "Uma estimativa precisa explicitar período, método ou incerteza.", pergunta=pergunta, campo="qualificacao_estimativa", recomendacao="Qualificar o recorte e a incerteza da estimativa."))
    elif pergunta.natureza_resposta == "EXATA" and _texto(pergunta.qualificacao_estimativa):
        achados.append(_achado("QUALIFICACAO_DESNECESSARIA", "AVISO", "Uma resposta exata possui qualificação de estimativa.", pergunta=pergunta, campo="qualificacao_estimativa", recomendacao="Confirmar a natureza da resposta ou remover a qualificação."))
    if not _texto(pergunta.tema_editorial):
        achados.append(_achado("TEMA_EDITORIAL_AUSENTE", "ERRO", "O tema editorial é obrigatório para o Nem a Pato.", pergunta=pergunta, campo="tema_editorial", recomendacao="Informar o tema editorial."))
    if pergunta.fonte_url and not _url_http_valida(pergunta.fonte_url):
        achados.append(_achado("URL_FONTE_LEGADA_INVALIDA", "AVISO", "A URL da fonte legada é estruturalmente inválida.", pergunta=pergunta, campo="fonte_url", recomendacao="Corrigir ou remover o metadado legado; as referências estruturadas são preservadas."))


def _detectar_duplicidades(perguntas, achados):
    por_texto = defaultdict(list)
    for item in perguntas:
        texto = _normalizar(item.enunciado)
        if texto:
            por_texto[texto].append(item)
    for itens in por_texto.values():
        if len(itens) > 1:
            ids = ", ".join(item.id_editorial for item in itens)
            for item in itens:
                achados.append(_achado("ENUNCIADO_DUPLICADO", "ERRO", f"Enunciado normalizado repetido entre: {ids}.", pergunta=item, campo="enunciado", recomendacao="Manter apenas perguntas editorialmente distintas."))

    # Bloqueia candidatos por prefixo normalizado; evita comparar todos os pares.
    blocos = defaultdict(list)
    for item in perguntas:
        texto = _normalizar(item.enunciado)
        tokens = texto.split()
        chave = " ".join(tokens[:3])
        if chave:
            blocos[chave].append((item, texto, set(tokens)))
    avisados = set()
    for bloco in blocos.values():
        for indice, (a, texto_a, tokens_a) in enumerate(bloco):
            for b, texto_b, tokens_b in bloco[indice + 1:]:
                if texto_a == texto_b:
                    continue
                jaccard = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
                similaridade = SequenceMatcher(None, texto_a, texto_b).ratio() if jaccard >= .6 else 0
                if max(jaccard, similaridade) >= .86:
                    par = tuple(sorted((str(a.id), str(b.id))))
                    if par in avisados:
                        continue
                    avisados.add(par)
                    mensagem = f"Possível duplicidade com {b.id_editorial} ({max(jaccard, similaridade):.0%} de similaridade)."
                    achados.append(_achado("ENUNCIADO_SEMELHANTE", "AVISO", mensagem, pergunta=a, campo="enunciado", recomendacao="Comparar manualmente os dois enunciados."))


def validar_rascunho_oficial(db: Session, rascunho_id):
    rascunho = db.get(CatalogoOficialRascunho, rascunho_id)
    if rascunho is None:
        return None
    modelo = PerguntaQuizRascunho if rascunho.modo == "QUIZ_CLASSICO" else PerguntaNemPatoRascunho
    perguntas = list(db.scalars(
        select(modelo).options(selectinload(modelo.fontes))
        .where(modelo.rascunho_id == rascunho.id).order_by(modelo.ordem, modelo.id)
    ))
    categorias = {item.id: item for item in db.scalars(select(Categoria).where(Categoria.id.in_({p.categoria_id for p in perguntas})))} if perguntas else {}
    achados = []

    origem = db.get(CatalogoOficial, rascunho.catalogo_origem_id)
    if origem is None:
        achados.append(_achado("CATALOGO_ORIGEM_INEXISTENTE", "ERRO", "O catálogo de origem não existe.", campo="catalogo_origem_id"))
    elif origem.modo != rascunho.modo or origem.catalogo_id != rascunho.catalogo_id or origem.versao != rascunho.versao_base:
        achados.append(_achado("CATALOGO_ORIGEM_DIVERGENTE", "ERRO", "Os metadados do rascunho divergem do catálogo de origem.", campo="catalogo_origem_id"))

    ids = Counter(_texto(item.id_editorial) for item in perguntas)
    ordens = Counter(item.ordem for item in perguntas)
    for item in perguntas:
        if ids[_texto(item.id_editorial)] > 1:
            achados.append(_achado("ID_EDITORIAL_DUPLICADO", "ERRO", "O ID editorial está repetido no rascunho.", pergunta=item, campo="id_editorial"))
        if ordens[item.ordem] > 1:
            achados.append(_achado("ORDEM_PERGUNTA_DUPLICADA", "ERRO", "A ordem da pergunta está repetida no rascunho.", pergunta=item, campo="ordem"))
        if item.tipo_alteracao == "REMOVIDA":
            achados.append(_achado("PERGUNTA_REMOVIDA", "INFORMACAO", "A pergunta está removida logicamente e não contará para publicação.", pergunta=item, campo="tipo_alteracao"))
            continue
        (_validar_quiz if rascunho.modo == "QUIZ_CLASSICO" else _validar_nem_pato)(item, categorias.get(item.categoria_id), achados)
        if item.tipo_alteracao in {"ADICIONADA", "MODIFICADA"}:
            achados.append(_achado(f"PERGUNTA_{item.tipo_alteracao}", "INFORMACAO", f"A pergunta está marcada como {item.tipo_alteracao.lower()} no rascunho.", pergunta=item, campo="tipo_alteracao"))

    publicaveis = [item for item in perguntas if item.tipo_alteracao != "REMOVIDA"]
    _detectar_duplicidades(publicaveis, achados)
    if not publicaveis:
        achados.append(_achado("RASCUNHO_SEM_PERGUNTAS", "ERRO", "O rascunho não possui perguntas que seriam publicadas.", recomendacao="Adicionar ou restaurar perguntas antes de uma futura publicação."))

    por_categoria = Counter(item.categoria_slug_snapshot for item in publicaveis)
    for slug, total in sorted(por_categoria.items()):
        achados.append(_achado("DISTRIBUICAO_CATEGORIA", "INFORMACAO", f"A categoria {slug} possui {total} pergunta(s) publicável(is).", campo="categoria_id"))
    if rascunho.modo == "QUIZ_CLASSICO":
        for dificuldade, total in sorted(Counter(item.dificuldade for item in publicaveis).items()):
            achados.append(_achado("DISTRIBUICAO_DIFICULDADE", "INFORMACAO", f"A dificuldade {dificuldade} possui {total} pergunta(s).", campo="dificuldade"))

    perguntas_com_erro = {item["pergunta_id"] for item in achados if item["nivel"] == "ERRO" and item["pergunta_id"]}
    perguntas_com_problema = {item["pergunta_id"] for item in achados if item["nivel"] in {"ERRO", "AVISO"} and item["pergunta_id"]}
    return {
        "rascunho_id": rascunho.id, "catalogo_origem_id": rascunho.catalogo_origem_id,
        "catalogo_id": rascunho.catalogo_id, "versao_base": rascunho.versao_base,
        "modo": rascunho.modo, "revisao_validada": rascunho.revisao,
        "resumo": {
            "perguntas_examinadas": len(perguntas), "perguntas_publicaveis": len(publicaveis),
            "perguntas_validas_estruturalmente": len(publicaveis) - len(perguntas_com_erro),
            "perguntas_com_problemas": len(perguntas_com_problema),
            "erros": sum(a["nivel"] == "ERRO" for a in achados),
            "avisos": sum(a["nivel"] == "AVISO" for a in achados),
            "informacoes": sum(a["nivel"] == "INFORMACAO" for a in achados),
        },
        "achados": achados,
    }
