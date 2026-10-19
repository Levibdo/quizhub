# Catálogos oficiais versionados

Os arquivos finais homologados são `quiz_classico_v2.json` e
`nem_a_pato_macabro_v1.json`.

O contrato executável está em
`app.services.validador_catalogos_oficiais`. O `manifest.json` registra os
arquivos canônicos, seus hashes SHA-256 e o status `PRONTO`.

## Quiz Clássico v2

O objeto raiz contém `schema_version`, `catalogo_id`, `versao`, `modo` e
`categorias`. As categorias obrigatórias são `geral`, `tecnologia`,
`matematica` e `entretenimento`. Cada categoria contém exatamente 100
perguntas: 30 `FACIL`, 45 `MEDIA` e 25 `DIFICIL`.

Cada pergunta contém `id_editorial`, `enunciado`, `dificuldade`, quatro
`alternativas`, `resposta_correta` (índice de 0 a 3), `explicacao` e uma ou
mais `fontes`. Cada fonte contém `titulo`, URL HTTP(S) e `acessada_em`.

## Nem a Pato — Macabro v1

O objeto raiz contém `schema_version`, `catalogo_id`, `versao`, `modo` e uma
única `categoria`, cujo slug é `macabro`. Ela contém exatamente 100 perguntas.

Cada pergunta contém `id_editorial`, `enunciado`, `resposta_numerica` inteira
no intervalo BIGINT não negativo, `unidade`, `explicacao`, `tema_editorial`,
`natureza_resposta` (`EXATA` ou `ESTIMATIVA`),
`qualificacao_estimativa` e uma ou mais `fontes`. Uma estimativa exige
qualificação explícita; a existência de uma URL não substitui curadoria humana.

## Dry-run

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m app.cli catalogo-oficial validar \
  --quiz-classico dados_oficiais/quiz_classico_v2.json \
  --nem-a-pato dados_oficiais/nem_a_pato_macabro_v1.json \
  --manifesto dados_oficiais/manifest.json
```

O comando não abre sessão de banco, imprime hashes SHA-256 e retorna código
diferente de zero quando encontra erro impeditivo. Similaridades são avisos
para revisão humana, não rejeições automáticas.
