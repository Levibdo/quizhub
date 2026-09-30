from dataclasses import dataclass


QUANTIDADE_MAXIMA_PROMPT = 100
DIFICULDADES = ("Fácil", "Média", "Difícil", "Mista")
PUBLICO_PADRAO = "Público geral"


class ParametrosPromptInvalidos(ValueError):
    pass


@dataclass(frozen=True)
class ParametrosPrompt:
    categoria_id: str
    tema: str
    quantidade: int
    dificuldade: str
    publico_alvo: str = PUBLICO_PADRAO


def gerar_prompt_perguntas(parametros: ParametrosPrompt) -> str:
    categoria_id = _texto_obrigatorio(
        parametros.categoria_id, "categoria_id"
    )
    tema = _texto_obrigatorio(parametros.tema, "tema")
    publico_alvo = (
        parametros.publico_alvo.strip()
        if isinstance(parametros.publico_alvo, str)
        else ""
    ) or PUBLICO_PADRAO

    quantidade = parametros.quantidade
    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        raise ParametrosPromptInvalidos("quantidade deve ser um número inteiro")
    if quantidade <= 0:
        raise ParametrosPromptInvalidos("quantidade deve ser maior que zero")
    if quantidade > QUANTIDADE_MAXIMA_PROMPT:
        raise ParametrosPromptInvalidos(
            f"quantidade máxima é {QUANTIDADE_MAXIMA_PROMPT}"
        )

    dificuldade = _normalizar_dificuldade(parametros.dificuldade)
    orientacao_mista = (
        "\n- Quando a dificuldade for Mista, distribua as perguntas de forma "
        "aproximadamente equilibrada entre níveis fácil, médio e difícil."
        if dificuldade == "Mista"
        else ""
    )

    return f"""Crie um conjunto de perguntas para o QuizHub com estas características:
- categoria_id: {categoria_id}
- tema: {tema}
- quantidade: exatamente {quantidade} perguntas
- dificuldade: {dificuldade}
- público-alvo: {publico_alvo}

Retorne exclusivamente um objeto JSON válido com este contrato exato:
{{
  "modo": "quiz_classico",
  "categoria_id": "{categoria_id}",
  "perguntas": [
    {{
      "enunciado": "...",
      "alternativas": ["...", "...", "...", "..."],
      "alternativa_correta": 0,
      "explicacao": "..."
    }}
  ]
}}

Regras obrigatórias:
- Gere exatamente {quantidade} perguntas.
- Preserve "modo" exatamente como "quiz_classico".
- Preserve "categoria_id" exatamente como "{categoria_id}".
- Cada pergunta deve ter exatamente 4 alternativas.
- Deve existir apenas uma alternativa correta por pergunta.
- "alternativa_correta" deve ser um índice numérico 0, 1, 2 ou 3.
- A explicação é obrigatória, breve e deve justificar por que a resposta está correta.
- Use enunciados claros, objetivos e baseados em fatos verificáveis.
- Evite questões ambíguas ou cuja resposta dependa excessivamente de opinião.
- Adeque a dificuldade ao nível {dificuldade} e a linguagem ao público {publico_alvo}.{orientacao_mista}
- Cada pergunta deve ser independente das demais e compreensível sem depender de outra pergunta do conjunto.
- Não repita perguntas nem produza duplicações semânticas no conjunto.
- Evite alternativas obviamente absurdas; as incorretas devem ser plausíveis.
- Distribua a posição da alternativa correta ao longo do conjunto, sem usar sempre o mesmo índice.
- Não acrescente campos ao contrato apresentado.
- Não inclua Markdown nem cercas de código como ```json.
- Não inclua introdução, comentários ou texto depois do JSON.
- Retorne somente o objeto JSON válido."""


def _texto_obrigatorio(valor: object, campo: str) -> str:
    texto = valor.strip() if isinstance(valor, str) else ""
    if not texto:
        raise ParametrosPromptInvalidos(f"{campo} é obrigatório")
    return texto


def _normalizar_dificuldade(valor: object) -> str:
    texto = valor.strip().casefold() if isinstance(valor, str) else ""
    for dificuldade in DIFICULDADES:
        if texto == dificuldade.casefold():
            return dificuldade
    opcoes = ", ".join(DIFICULDADES)
    raise ParametrosPromptInvalidos(
        f"dificuldade deve ser uma destas opções: {opcoes}"
    )
