# Homologação da publicação incremental

## Escopo

Homologação local do fluxo administrativo de criação, edição,
revisão, aprovação e publicação incremental de catálogos oficiais.
Nenhum banco persistente ou serviço de produção foi usado.

## Ambiente

- branch: `feat/incremental-catalog-publishing`
- commit de base observado: `7a4059767dc4eaa447dc217a199c4ff25b54e877`
- frontend React/Vite local
- backend FastAPI local
- PostgreSQL 16 descartável fora da porta 5432
- Chrome real controlado por Playwright
- Alembic head: `0022`

## Cenários executados

1. Criação de um catálogo inicial vazio pela interface administrativa.
2. Inclusão de 15 perguntas Nem a Pato com fontes estruturadas.
3. Revisão e aprovação das 15 perguntas pela interface.
4. Publicação da primeira versão incremental com 15 perguntas.
5. Clonagem da versão ativa para um novo rascunho.
6. Preservação das 15 anteriores como `INALTERADA` e inclusão de mais 15.
7. Revisão somente das 15 perguntas novas.
8. Publicação da segunda versão com 30 perguntas, sem duplicidade.
9. Recarregamento da interface e confirmação da persistência.
10. Consulta do histórico de versões e da auditoria administrativa.
11. Publicação de uma versão posterior durante partida Nem a Pato em
    andamento, preservando as rodadas vinculadas à versão arquivada.

## Resultados

- Fluxo 15 → 30 concluído no navegador real.
- Versões anteriores preservadas e consultáveis.
- Fontes estruturadas preservadas.
- Perguntas inalteradas dispensadas de nova revisão.
- Auditoria, idempotência, concorrência e rollback transacional aprovados.
- Snapshot de partida em andamento preservado durante a troca de versão.
- Catálogo ativo vazio não permite iniciar partidas: o Quiz Clássico e o
  Nem a Pato exigem dez perguntas elegíveis e não deixam estado parcial.

## Evidências

As capturas válidas foram copiadas para [`evidencias/`](evidencias/). Arquivos
marcados como erro existentes no diretório temporário não foram incorporados.

| Arquivo | Evidência |
|---|---|
| `01-catalogo-inicial-vazio.png` | Estado inicial sem perguntas |
| `02-primeiro-rascunho-15.png` | Primeiro rascunho com 15 perguntas |
| `03-primeiro-lote-revisado.png` | Revisão do primeiro lote |
| `04-primeira-versao-publicada.png` | Primeira versão publicada |
| `05-segundo-rascunho-15-inalteradas.png` | Perguntas anteriores inalteradas |
| `06-segundo-rascunho-30.png` | Segundo rascunho totalizando 30 |
| `07-segunda-versao-publicada.png` | Segunda versão publicada |
| `08-persistencia-apos-reload.png` | Persistência após recarregamento |
| `09-auditoria-publicacoes.png` | Auditoria administrativa |
| `10-partida-em-andamento-antes-da-troca.png` | Partida antes da troca |
| `11-publicacao-durante-partida.png` | Publicação durante a partida |

## Limitações e pendências

- O catálogo inicial vazio é um recurso de preparação administrativa e
  não é jogável até possuir ao menos dez perguntas elegíveis.
- A migration `0022` ainda precisa de backup validado e aplicação controlada
  antes de uma futura implantação.
- A implantação não fez parte desta homologação.
