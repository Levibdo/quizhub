# QuizHub

O QuizHub é uma aplicação web de quiz desenvolvida inicialmente como projeto acadêmico. O jogo oferece partidas de múltipla escolha organizadas por categoria, tempo por pergunta, pontuação e ranking.

## Funcionalidades

- Identificação do jogador por nome ou apelido.
- Escolha entre as categorias Geral, Tecnologia, Matemática e Entretenimento.
- Catálogo oficial atual com 139 perguntas: 35 em Geral, Matemática e Tecnologia, e 34 em Entretenimento.
- Partidas com 10 perguntas selecionadas aleatoriamente e sem repetição.
- Limite de 15 segundos por pergunta.
- Feedback visual por aproximadamente 2 segundos após cada resposta.
- Destaque da alternativa escolhida e da alternativa correta depois da resposta.
- Pontuação baseada no acerto e no tempo restante.
- Resultado final com pontuação, acertos e erros.
- Ranking local armazenado no navegador com `localStorage`.
- Backend autoritativo para seleção das perguntas, validação das respostas, pontuação, timeout, progressão e finalização da partida.
- Importação de perguntas em formato XLSX.
- Proteção contra duplicação no importador pela combinação `categoria_id` + `enunciado`.

## Sistema de pontuação

O backend calcula a pontuação de cada resposta correta pela fórmula:

```text
100 + (tempo restante em segundos × 10)
```

- Resposta errada ou timeout: 0 pontos.
- Pontuação máxima por pergunta: 250 pontos.

O prazo e a pontuação são determinados pelo servidor, e não pelo contador visual do navegador.

## Arquitetura

```text
React/Vite
    ↓ HTTP
FastAPI
    ↓
PostgreSQL
```

- **React/Vite:** apresenta as telas, envia as ações do jogador e exibe o estado retornado pela API.
- **FastAPI:** controla as partidas, seleciona as perguntas, valida respostas e timeouts, calcula a pontuação e decide quando a partida termina.
- **PostgreSQL:** persiste o catálogo e os dados operacionais das partidas.

O frontend recebe somente o enunciado e as alternativas antes da resposta. A alternativa correta é revelada pela API apenas depois que o jogador responde ou o prazo termina.

## Tecnologias

- React
- Vite
- JavaScript
- FastAPI
- Python
- PostgreSQL
- SQLAlchemy
- Alembic
- psycopg
- openpyxl

## Estrutura do projeto

```text
quizhub/
├── backend/
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── api/
│   │   ├── data/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── dados/
│   │   ├── perguntas_carga_inicial.xlsx
│   │   └── perguntas_expansao_105.xlsx
│   ├── tests/
│   ├── alembic.ini
│   └── requirements.txt
├── public/
├── src/
│   ├── components/
│   ├── data/
│   ├── services/
│   └── utils/
├── package.json
├── vite.config.js
└── README.md
```

O diretório `backend/dados/` armazena os catálogos versionados. Para o schema atual, o catálogo recomendado é `perguntas_oficiais_com_explicacoes.xlsx`, com 105 perguntas (35 em cada uma das categorias Geral, Matemática e Tecnologia). `perguntas_entretenimento.json` contém atualmente 34 perguntas, totalizando 139. A planilha `perguntas_oficiais.xlsx`, sem explicações, não é o catálogo recomendado porque `explicacao` é obrigatória no schema atual.

## Banco de dados

O PostgreSQL persiste:

- jogadores;
- categorias;
- perguntas;
- partidas;
- perguntas selecionadas para cada partida;
- respostas dos jogadores.

A conexão é configurada pela variável de ambiente `DATABASE_URL`. Use suas próprias credenciais; por exemplo:

```text
postgresql+psycopg://USUARIO:SENHA@localhost:5432/quiz_estagio_db
```

## Como executar

### 1. Pré-requisitos

- Python
- Node.js e npm
- PostgreSQL em execução

### 2. Backend

No Windows PowerShell, a partir da raiz do projeto:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://USUARIO:SENHA@localhost:5432/quiz_estagio_db"
python -m alembic upgrade head
python -m app.cli perguntas validar dados/perguntas_oficiais_com_explicacoes.xlsx
python -m app.cli perguntas importar dados/perguntas_oficiais_com_explicacoes.xlsx
python -m app.cli perguntas validar dados/perguntas_entretenimento.json
python -m app.cli perguntas importar dados/perguntas_entretenimento.json
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

No Linux ou macOS, ative o ambiente virtual com `source .venv/bin/activate` e defina a conexão com:

```bash
export DATABASE_URL="postgresql+psycopg://USUARIO:SENHA@localhost:5432/quiz_estagio_db"
```

As migrations cadastram as quatro categorias-base necessárias aos catálogos. Categorias adicionais continuam dinâmicas e podem ser criadas pelo CLI. Não é necessário executar o seed para importar os catálogos oficiais.

O comando `python -m app.db.seed` permanece disponível, de forma idempotente, apenas para desenvolvimento e demonstração: ele cadastra categorias-base ausentes e 15 perguntas de exemplo. Não o execute antes dos catálogos oficiais em uma instalação destinada a receber esses arquivos, pois as perguntas de exemplo serão detectadas como duplicadas durante a importação.

As categorias exibidas no frontend são carregadas do PostgreSQL pela API. Para
administrá-las localmente, execute os comandos abaixo dentro de `backend`, com
`DATABASE_URL` configurada:

```powershell
python -m app.cli categoria listar
python -m app.cli categoria criar
```

O comando `criar` solicita nome, código e descrição, mostra uma confirmação e
só então persiste a categoria. O código deve começar com uma letra minúscula e
usar somente letras minúsculas ASCII, números e hífens, com até 50 caracteres.

### 3. Frontend

Em outro terminal, a partir da raiz do projeto:

```powershell
npm install
npm run dev -- --host 0.0.0.0
```

O Vite usa por padrão a porta `5173`. A URL do backend pode ser definida antes de iniciar o frontend:

```powershell
$env:VITE_API_URL = "http://localhost:8001"
npm run dev -- --host 0.0.0.0
```

Sem `VITE_API_URL`, o frontend usa o hostname pelo qual foi acessado e a porta `8001` para localizar a API.

## Importação e validação das perguntas

O CLI administrativo aceita XLSX, CSV e JSON e detecta o formato pela extensão:

```powershell
cd backend
python -m app.cli perguntas validar caminho\perguntas.xlsx
python -m app.cli perguntas validar caminho\perguntas.csv
python -m app.cli perguntas validar caminho\perguntas.json

python -m app.cli perguntas importar caminho\perguntas.xlsx
python -m app.cli perguntas importar caminho\perguntas.csv
python -m app.cli perguntas importar caminho\perguntas.json
```

`validar` consulta categorias e duplicidades, mas não insere, atualiza, exclui ou
faz commit de dados. `importar` mostra primeiro o mesmo relatório de validação e
solicita confirmação antes de persistir somente perguntas válidas e não
duplicadas.

O endpoint de importação é:

```text
POST /api/v1/perguntas/importar
```

Com o backend em execução, abra [http://localhost:8001/docs](http://localhost:8001/docs), localize o endpoint e envie uma planilha `.xlsx` no campo de arquivo. Para preservar o contrato público existente, esse endpoint continua aceitando somente XLSX; CSV e JSON estão disponíveis pelo CLI.

### XLSX e CSV

A primeira linha deve conter estas colunas:

```text
categoria_id
enunciado
alternativa_a
alternativa_b
alternativa_c
alternativa_d
alternativa_correta
explicacao
```

O CSV oficial usa vírgula como delimitador, codificação UTF-8 com ou sem BOM e
segue as regras usuais de aspas do formato para textos que contenham vírgulas.

O campo `alternativa_correta` usa índices iniciados em zero:

- `0` = A
- `1` = B
- `2` = C
- `3` = D

O importador valida cada linha e não insere uma pergunta quando já existe a mesma combinação de `categoria_id` e `enunciado`. A duplicata é informada no relatório da importação, e o registro existente não é alterado.

### JSON

O contrato JSON oficial é:

```json
{
  "modo": "quiz_classico",
  "categoria_id": "entretenimento",
  "perguntas": [
    {
      "enunciado": "Qual filme...?",
      "alternativas": [
        "Alternativa A",
        "Alternativa B",
        "Alternativa C",
        "Alternativa D"
      ],
      "alternativa_correta": 0,
      "explicacao": "Explicação breve da resposta."
    }
  ]
}
```

`modo` deve ser exatamente `quiz_classico`, `categoria_id` identifica uma
categoria ativa, `perguntas` deve ser uma lista não vazia e cada pergunta deve
ter exatamente quatro alternativas. `alternativa_correta` é um índice de 0 a 3
e `explicacao` é obrigatória.

JSON é o formato recomendado para conteúdo produzido externamente com auxílio
de ChatGPT, Gemini ou outras ferramentas. O QuizHub não possui integração
direta com nenhuma IA: o arquivo deve ser revisado e validado pelo CLI antes da
importação.

### Gerador de prompt para IA externa

O CLI pode montar um prompt compatível com o contrato JSON do importador:

```powershell
cd backend
python -m app.cli prompt gerar
```

O fluxo consulta as categorias ativas no PostgreSQL e solicita categoria, tema,
quantidade, dificuldade e público-alvo. A quantidade deve estar entre 1 e 100.
O limite de 100 mantém os lotes administráveis e reduz o risco de uma ferramenta
externa truncar a resposta. Pressionar Enter no público-alvo usa `Público geral`.

Exemplo resumido:

```text
Categorias ativas:
1. Entretenimento (entretenimento)
Categoria (número ou id): entretenimento
Tema: Cinema, séries, música e cultura pop
Quantidade de perguntas: 34
Dificuldade: 4
Público-alvo [Público geral]: Universitários

----- PROMPT GERADO -----
...
----- FIM DO PROMPT -----
```

O comando somente imprime texto. Ele não chama ChatGPT, Gemini ou qualquer API,
não exige chave e não grava perguntas nem arquivos. O processo administrativo é:

```text
QuizHub gera o prompt
→ o usuário usa a IA externa escolhida
→ a IA retorna JSON
→ o usuário salva o JSON em um arquivo
→ o QuizHub valida
→ o usuário confirma a importação
```

Depois de revisar e salvar a resposta da IA, use:

```powershell
python -m app.cli perguntas validar arquivo.json
python -m app.cli perguntas importar arquivo.json
```

## Catálogo numérico Nem a Pato

O catálogo de perguntas numéricas usa a tabela `perguntas_nem_pato` e um
importador separado do Quiz Clássico. Nesta fase há somente infraestrutura de
catálogo/CLI; não há API nem gameplay Nem a Pato.

O formato canônico aceita XLSX, CSV e JSON. XLSX/CSV usam a primeira linha
como cabeçalho; são obrigatórias `categoria_id`, `enunciado`,
`resposta_numerica` e `explicacao`. `unidade`, `fonte` e `ativa` são opcionais.
Colunas adicionais são ignoradas. CSV usa vírgula, aspas CSV padrão e UTF-8
com ou sem BOM. JSON deve ser uma lista de objetos com os mesmos nomes de
campos. Uma lista JSON vazia é válida e contém zero itens; arquivo vazio ou
XLSX/CSV sem cabeçalho é inválido. Linhas de planilha completamente vazias
são ignoradas e fórmulas na coluna `resposta_numerica` são rejeitadas.

`resposta_numerica` aceita inteiros não negativos e texto decimal composto
somente por dígitos ASCII (por exemplo, `"40075"`). XLSX também aceita célula
numérica inteira, dentro do limite de precisão inteira segura do Excel; frações,
booleanos, `NaN`, infinito, texto inválido e valores acima do limite `BIGINT`
são rejeitados. `ativa` aceita booleano, `true`/`false`, `1`/`0`, `sim`/`não`
ou `s`/`n`, sem distinção de caixa; ausente ou vazio significa `true`.

A duplicata é definida por `(categoria_id, enunciado)` após trim das
extremidades, com comparação sensível a maiúsculas/minúsculas. Duplicatas do
arquivo e do banco são reportadas e ignoradas; registros existentes nunca são
atualizados. A validação não grava dados. A importação exige confirmação e é
toda-ou-nada: qualquer registro inválido cancela o lote, enquanto duplicatas
conhecidas podem ser ignoradas. Erros durante a persistência provocam rollback.

Comandos, executados no diretório `backend`:

```text
python -m app.cli nem-pato perguntas validar arquivo.xlsx
python -m app.cli nem-pato perguntas importar arquivo.csv
python -m app.cli nem-pato perguntas listar
python -m app.cli nem-pato perguntas resumo
python -m app.cli nem-pato perguntas criar
```

`listar` não exibe as respostas numéricas. `criar` solicita os mesmos campos
e usa as mesmas validações e detecção de duplicata da importação.

## Lobby Nem a Pato

O backend oferece endpoints do lobby, prepara a partida e permite abrir a
primeira rodada com palpites numéricos crescentes:

| Método | Endpoint | Finalidade |
| --- | --- | --- |
| `POST` | `/api/v1/nem-pato/salas` | Cria sala e primeiro participante anfitrião. |
| `POST` | `/api/v1/nem-pato/salas/{codigo}/participantes` | Entra em sala aguardando. |
| `GET` | `/api/v1/nem-pato/salas/{codigo}` | Consulta estado público do lobby. |
| `GET` | `/api/v1/nem-pato/salas/{codigo}/eu` | Recupera a participação autenticada após F5. |
| `POST` | `/api/v1/nem-pato/salas/{codigo}/iniciar` | Anfitrião inicia e prepara 10 rodadas. |
| `POST` | `/api/v1/nem-pato/salas/{codigo}/rodadas/iniciar` | Anfitrião abre a primeira rodada. |
| `POST` | `/api/v1/nem-pato/salas/{codigo}/rodadas/{rodada_id}/palpites` | Jogador da vez registra um palpite. |
| `POST` | `/api/v1/nem-pato/salas/{codigo}/rodadas/{rodada_id}/desafiar` | Jogador elegível resolve a rodada contra o último palpite. |
| `POST` | `/api/v1/nem-pato/salas/{codigo}/rodadas/{rodada_id}/proxima` | Anfitrião ativo abre a próxima rodada após o resultado. |
| `POST` | `/api/v1/nem-pato/salas/{codigo}/abandonar` | Abandona explicitamente e transfere anfitrião se necessário. |

O código de sala tem seis caracteres maiúsculos e usa o alfabeto
`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`; é identificador, não credencial. Criação e
entrada devolvem uma credencial aleatória opaca uma única vez. O banco guarda
somente seu digest SHA-256. Endpoints privados usam `X-Nem-Pato-Token`, separado
do cookie JWT de conta QuizHub. Um cliente pode guardar o token localmente e
usar `GET /eu` após recarregar a página; recarregar não abandona a sala.

O lobby aceita até seis participantes ativos; mínimo de três é requisito para
uma partida futura. O serviço normaliza nome com trim, limita a 100 caracteres
e trata diferenças de caixa simples como duplicatas. Ordens de entrada não são
reutilizadas. Abandono preserva o registro e transfere o anfitrião ao ativo de
menor ordem. Alterações de entrada e abandono incrementam uma vez a versão da
sala. Operações de alteração bloqueiam primeiro a linha da sala e depois os
participantes relacionados no PostgreSQL.

O anfitrião pode iniciar quando há de 3 a 6 participantes ativos. O backend
seleciona 10 perguntas numéricas ativas distintas, cria os snapshots dos
jogadores e prepara 10 rodadas em `AGUARDANDO_INICIO`, sem deadline ou turno
ativo. A sala muda para `EM_PARTIDA` e incrementa sua versão na mesma transação.
Os clientes recuperam um resumo seguro da partida por `GET .../eu`; o DTO não
inclui perguntas nem respostas. Nesta etapa, a categoria da partida registra
a categoria da primeira pergunta selecionada (as categorias das demais
perguntas podem variar). Durante uma rodada ativa, o abandono permanece bloqueado. Entre rodadas, em
`RESULTADO`, o participante pode abandonar: seu snapshot é marcado, ele deixa as
rotações futuras e, se era anfitrião, o papel passa ao próximo participante ativo.

O início da rodada revela somente enunciado, categoria e unidade da pergunta;
`resposta_numerica` e `explicacao` permanecem privadas. O primeiro jogador é
derivado da ordem circular dos snapshots e do número da rodada. Cada palpite
deve ser inteiro não negativo e estritamente maior que o anterior; depois de
aceito, o turno avança circularmente. O payload de palpite exige
`client_action_id` UUID, que torna seguro repetir a mesma ação sem criar outro
registro nem avançar o turno novamente. Início e palpites usam o header
`X-Nem-Pato-Token` e a ordem de locks sala → participantes → partida → rodada
→ snapshots → palpites.

O polling de `GET .../eu` devolve pergunta pública, jogador da vez, maior
palpite, histórico e placar de patos. Após ao menos um palpite, qualquer jogador
ativo do snapshot, inclusive fora de turno, pode desafiar o último palpite, exceto
o próprio autor. O payload exige `client_action_id` UUID persistido. Se o palpite
passou da resposta, seu autor recebe um pato; se ficou abaixo ou foi exatamente
igual, o desafiante recebe o pato. A igualdade, portanto, favorece o autor.

Palpite e desafio usam a mesma ordem de locks e o backend escolhe o último palpite
sob lock. Apenas uma resolução por rodada é persistida. Em `RESULTADO`, resposta,
explicação, autor, desafiante, penalizado e placar são revelados e reconstruídos
após F5. O anfitrião ativo avança uma única rodada por ação, de R1 até R10;
o backend preserva histórico e placar, escolhe o jogador inicial pela rotação
circular dos snapshots ativos e incrementa a versão da sala uma vez. Repetições
ou corridas de avanço não iniciam duas rodadas. Depois da R10 não há avanço nesta
fase. Cada rodada dura 120 segundos e `termina_em` é o prazo autoritativo.
O PostgreSQL fornece o instante de validação após os locks; o countdown local é
apenas visual. Não há worker: `GET .../eu`, palpites e desafios detectam
`agora >= termina_em` e convergem atomicamente para `RESULTADO`. Com palpite, o
autor do último fica protegido e todos os demais snapshots ativos recebem um pato;
sem palpite, ninguém é penalizado. Ações validadas após o prazo não são gravadas.
Pollings concorrentes aplicam a transição e `estado_versao` uma única vez. O
`finalizada_em` registra o instante efetivo da persistência, enquanto `termina_em`
continua sendo o prazo. A ordem de locks é sala → participantes → partida → rodada
→ snapshots → palpites. O frontend nunca finaliza a rodada nem revela dados por
conta própria. O encerramento da partida após a R10 ainda não faz parte desta fase.

## API

Principais endpoints:

| Método | Endpoint | Finalidade |
| --- | --- | --- |
| `POST` | `/api/v1/partidas` | Cria uma partida e disponibiliza a primeira pergunta. |
| `POST` | `/api/v1/partidas/{partida_id}/respostas` | Processa uma resposta ou timeout e devolve o novo estado autoritativo. |
| `GET` | `/api/v1/categorias` | Lista as categorias ativas disponíveis para partidas. |
| `POST` | `/api/v1/perguntas/importar` | Importa perguntas de uma planilha XLSX. |
| `GET` | `/health` | Informa se a API está ativa. |

A documentação interativa fica em [http://localhost:8001/docs](http://localhost:8001/docs).

## Testes

Para executar a suíte automatizada do backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
```

Os testes de concorrência real do Nem a Pato ficam separados da suíte SQLite.
Eles cobrem entrada, início de partida/rodada, início versus entrada, palpites
simultâneos, retries idempotentes, avanço concorrente, avanço versus abandono, pollings simultâneos e corridas de
palpite/desafio versus timeout.
Execute-os somente em um banco PostgreSQL descartável cujo nome comece
com `np3_test_`; a suíte recusa outros nomes e exige Alembic `0010`:

```bash
cd backend
createdb np3_test_local
export DATABASE_URL="postgresql+psycopg://USUARIO:SENHA@localhost:5432/np3_test_local"
python -m alembic upgrade 0010
export NEM_A_PATO_TEST_DATABASE_URL="$DATABASE_URL"
python -m unittest discover -s tests/integration -v
dropdb np3_test_local
```

Não aponte `NEM_A_PATO_TEST_DATABASE_URL` para o banco de desenvolvimento. Os
testes abrem sessões/conexões PostgreSQL independentes e observam a segunda
transação esperando pelo lock da linha da sala em `pg_stat_activity`.

Para validar o frontend, execute na raiz do projeto:

```powershell
npm run lint
npm run build
```

## Acesso em rede

O backend e o frontend podem escutar em `0.0.0.0`, permitindo acesso por outros dispositivos da rede. O frontend deve ser iniciado com `npm run dev -- --host 0.0.0.0`, e o backend com a opção `--host 0.0.0.0` mostrada anteriormente.

Para cenários em que a API esteja em outro host ou porta, configure `VITE_API_URL`. O backend aceita origens de desenvolvimento na porta `5173`, e origens adicionais podem ser informadas pela variável `CORS_ORIGINS`, separadas por vírgula.

## Estado atual

O MVP possui backend persistente, motor autoritativo de partidas, catálogo versionado com 139 perguntas em quatro categorias, partidas de 10 perguntas, frontend funcional e ranking local no navegador.

## Próximas evoluções

As possibilidades abaixo ainda não estão implementadas:

- ranking persistente no PostgreSQL;
- diferentes quantidades e modos de partida;
- novos modos de jogo;
- multiplayer;
- melhorias visuais;
- modo para eventos e apresentações;
- QR Code para entrada;
- leaderboard compartilhado.

## Projeto acadêmico

O QuizHub foi desenvolvido como projeto acadêmico e continua em evolução.
