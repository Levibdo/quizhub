# Projeto técnico — categorias oficiais versionadas (0023)

## Escopo e invariantes

1. `categorias.id` continua sendo a identidade lógica estável usada por filtros e
   agregações. Uma identidade nunca é reutilizada por outro modo.
2. Uma representação publicada de categoria pertence a exatamente um catálogo
   oficial e é imutável. O par `(catalogo_oficial_id, categoria_id)` e o slug no
   catálogo são únicos.
3. Perguntas oficiais publicadas apontam para a representação de categoria do
   mesmo catálogo. Perguntas privadas não apontam para versões oficiais.
   Perguntas oficiais anteriores ao catálogo versionado são a única exceção:
   permanecem sem ambos os vínculos e recebem `proveniencia_legada=true`.
4. Alterações editoriais ocorrem somente em categorias de rascunho. A publicação
   copia categorias e perguntas em uma única transação e não modifica versões
   publicadas anteriores.
5. Um rascunho não mistura modos. Categoria, pergunta, catálogo e rascunho devem
   ter o mesmo modo; essa invariável entre tabelas é validada pelo serviço dentro
   da transação (constraints SQL protegem as relações que cabem numa tabela).
6. Partidas agregam historicamente pela identidade lógica. Rótulos históricos
   são lidos dos snapshots, nunca do cadastro mutável de categorias.
7. A importação administrativa cria ou altera somente um rascunho. Ela nunca
   aprova, publica ou ativa um catálogo.
8. Escritas administrativas exigem ADMIN ativo, CSRF, `Idempotency-Key`,
   `If-Match` quando alteram um rascunho, transação e auditoria sanitizada.

## Modelo

### `categorias_oficiais_versoes`

Representação imutável da identidade `categorias.id` dentro de uma versão de
catálogo. Contém slug, nome, descrição, estado editorial e
`origem_backfill`. Possui FKs restritivas, unicidade por catálogo/identidade e
catálogo/slug. Perguntas oficiais apontam para seu `id`.

### `categorias_oficiais_rascunhos`

Representação editável pertencente a `catalogos_oficiais_rascunhos`. A
identidade lógica já existe em `categorias`; uma categoria adicionada recebe um
UUID definitivo e um registro lógico oficial inativo, mas só se torna elegível
quando o rascunho é publicado. O estado registra `INALTERADA`, `MODIFICADA`,
`ADICIONADA` ou `REMOVIDA`, com revisão otimista.

### Snapshots

`partidas`, `partida_perguntas` e `rodadas_nem_pato` passam a armazenar slug e
nome. `snapshot_categoria_backfill=true` declara que o texto foi preenchido a
partir do valor conhecido no momento da 0023 e não prova que esse era o rótulo
na data histórica. Novos snapshots usam `false`.

## Backfill

Para cada par determinístico de catálogo publicado e categoria usado por suas
perguntas, a migration cria uma versão com os valores atuais e
`origem_backfill=true`. Em seguida vincula cada pergunta oficial à versão do
seu próprio catálogo. Registros privados permanecem com vínculo nulo.

Perguntas oficiais que já chegarem à 0023 sem `catalogo_oficial_id` não são
associadas a um catálogo inferido. A migration preserva seus IDs e relações e
marca `proveniencia_legada=true`; `categoria_versao_id` também permanece nulo.
Esse marcador registra ausência de proveniência, não a substitui. A constraint
de proveniência admite exatamente três estados:

- oficial legado: marcador verdadeiro e ambos os vínculos nulos;
- oficial versionado: marcador falso e ambos os vínculos preenchidos;
- conteúdo privado: marcador falso e ambos os vínculos nulos.

Novas linhas recebem o marcador falso por padrão. Assim, uma nova pergunta
oficial só pode ser persistida com catálogo e categoria versionada completos.
Importações integrais de 400/100 perguntas também materializam as versões de
categoria na mesma transação; elas não voltam a produzir conteúdo legado.
Uma trigger criada depois do backfill impede inserir novas linhas marcadas como
legadas e torna o marcador histórico imutável. Uma FK composta garante ainda
que categoria lógica, versão de categoria e catálogo da pergunta pertençam ao
mesmo vínculo publicado.

Snapshots textuais existentes são preenchidos a partir da identidade lógica
atual e marcados como backfill. Nenhum rótulo histórico ausente é inventado.
Uma inconsistência que impeça associação unívoca aborta a migration.

## Publicação, reativação e concorrência

A publicação bloqueia a linha do rascunho e a coleção de catálogos, verifica a
revisão esperada, materializa versões de categorias, vincula as novas perguntas
e troca a versão ativa na mesma transação. A reativação apenas troca o catálogo
ativo e sincroniza a projeção corrente de `categorias`; não altera versões,
fontes, perguntas ou snapshots históricos.

## Importação JSON

O contrato inicial aceita JSON UTF-8 com modo, categorias, perguntas e fontes
estruturadas. A pré-visualização valida cada registro e devolve erros por caminho.
A confirmação exige o mesmo hash de conteúdo e cria um rascunho; não reutiliza o
importador privado ou o importador oficial legado. CSV e XLSX ficam fora da 0023.

## Compatibilidade e rollback

Consultas correntes continuam aceitando a identidade lógica. Consultas
históricas passam a preferir snapshots/versões. O downgrade remove somente os
vínculos e estruturas introduzidos pela 0023; ele não tenta reconstruir nomes
históricos. Antes da implantação deve haver backup restaurável, pois downgrade
de schema não substitui restauração operacional.
