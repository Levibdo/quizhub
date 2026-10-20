# QuizHub

O QuizHub é uma aplicação web de perguntas e jogos, com frontend React/Vite,
API FastAPI e persistência PostgreSQL. O projeto oferece o **Quiz Clássico**,
o multiplayer **Nem a Pato** e uma área autenticada de **Meu Conteúdo** para
gerenciar catálogos privados.

> Este documento descreve o que está implementado no repositório. Topologias,
> nomes de serviços, portas externas e caminhos de uma implantação específica
> não são requisitos universais do QuizHub.

## Funcionalidades

### Quiz Clássico

- Partidas de múltipla escolha com 10 perguntas sem repetição.
- Prazo de 15 segundos por pergunta, controlado pelo backend.
- Seleção das perguntas, correção, timeout, pontuação e progressão
  autoritativos no servidor.
- Pontuação por acerto: `100 + (segundos restantes × 10)`, até 250 pontos por
  pergunta.
- Revelação da resposta correta e da explicação somente depois da resposta ou
  do timeout.
- Categorias oficiais e, para usuários autenticados, categorias próprias
  elegíveis.
- Resultado com pontuação, acertos e erros.
- Ranking global das melhores partidas oficiais finalizadas, consultado pelo
  frontend em `GET /api/v1/ranking` e calculado a partir do PostgreSQL.
- Perfis visitantes usam o UUID pseudônimo `quizhub-visitante-id`, persistido
  no `localStorage` do navegador. Ele agrupa resultados futuros no ranking,
  mas não autentica o visitante nem é vinculado automaticamente a uma conta.

## Sistema de Ranking

O ranking do Quiz Clássico é público e tem o PostgreSQL como fonte oficial.
O frontend consulta a API ao abrir a classificação e ao trocar os filtros; a
chave legada `quizhub-ranking` pode continuar no `localStorage`, mas não é
usada como fallback quando a API falha.

### Pontuação e elegibilidade

- Cada partida possui 10 perguntas e cada resposta correta vale
  `100 + (segundos restantes × 10)` pontos. O backend arredonda a diferença
  positiva até o prazo para cima e limita o resultado ao intervalo de 0 a 15,
  portanto cada questão vale de 100 a 250 pontos e uma partida pode chegar a
  2.500 pontos.
- Resposta incorreta ou timeout vale zero. Pontuação, acertos e erros são
  calculados e persistidos pelo backend; o cliente não envia o resultado a
  ser classificado.
- Entram no ranking somente partidas com status `FINALIZADA`, pertencentes à
  temporada consultada e a categorias de origem `OFICIAL`, modo
  `QUIZ_CLASSICO` e não excluídas logicamente.
- Categorias privadas e partidas do Nem a Pato nunca entram nesse ranking.
  Uma categoria oficial posteriormente desativada continua elegível no
  histórico; exclusão lógica, por outro lado, a remove das consultas.

### Identidade, melhor partida e classificação

Cada identidade aparece no máximo uma vez por consulta, representada por sua
melhor partida na temporada e no filtro escolhidos:

1. usuário autenticado: agrupamento por `usuarios.id`;
2. visitante atual: agrupamento pelo `visitante_id` UUID persistido no perfil
   do navegador;
3. visitante histórico sem UUID: identidade individual por `jogadores.id`,
   sem tentativa de agrupar retroativamente nomes iguais.

O `visitante_id` não é autenticação, não concede acesso a partidas e não é
vinculado automaticamente a uma conta criada depois. Dois navegadores com o
mesmo nome continuam sendo identidades diferentes; apagar o armazenamento
local cria outra identidade para partidas futuras.

A melhor partida de cada identidade e a classificação final usam, nesta
ordem:

1. maior pontuação;
2. maior quantidade de acertos;
3. conclusão mais antiga;
4. menor UUID da partida, como desempate determinístico.

Partidas históricas `FINALIZADA` sem `finalizada_em` são aceitas para
compatibilidade, mas ficam depois das partidas datadas quando os demais
critérios empatam. As posições retornadas são sequenciais dentro do resultado
limitado, sem compartilhar posição em empates.

### Ranking global, categorias e temporadas

`GET /api/v1/ranking` usa a temporada `ATIVA` por padrão. A migration `0013`
criou a Temporada 1, associou as partidas históricas existentes a ela e
adicionou proteção para existir no máximo uma temporada ativa. Novas partidas
recebem a temporada ativa no servidor; o cliente não escolhe nem altera essa
associação.

Parâmetros públicos:

| Parâmetro | Formato | Comportamento |
| --- | --- | --- |
| `categoria` | slug ou UUID | Restringe a uma categoria oficial elegível. |
| `temporada` | número positivo ou UUID | Consulta uma temporada ativa ou encerrada. Temporadas planejadas não são públicas. |
| `limit` | inteiro de 1 a 100 | Padrão `10`; o limite é aplicado na consulta SQL. |

Exemplos:

```http
GET /api/v1/ranking?limit=10
GET /api/v1/ranking?categoria=tecnologia&temporada=1&limit=20
GET /api/v1/ranking/temporadas
```

Resposta ilustrativa, sem dados reais:

```json
[
  {
    "posicao": 1,
    "jogador": "Jogador exemplo",
    "categoria": {
      "id": "11111111-2222-4333-8444-555555555555",
      "slug": "tecnologia",
      "nome": "Tecnologia"
    },
    "pontuacao": 2150,
    "acertos": 9,
    "erros": 1,
    "finalizada_em": "2026-01-15T18:30:00Z"
  }
]
```

`GET /api/v1/ranking/temporadas` lista temporadas `ATIVA` e `ENCERRADA`, com
a ativa primeiro, e expõe `id`, `numero`, `nome`, `status`, `inicia_em` e
`encerra_em`:

```json
[
  {
    "id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    "numero": 1,
    "nome": "Temporada 1",
    "status": "ATIVA",
    "inicia_em": "2026-01-01T00:00:00Z",
    "encerra_em": null
  }
]
```

Temporada inexistente ou planejada no filtro retorna `404`; limites fora do
intervalo retornam `422`. Pela implementação atual, se não existir temporada
ativa, a consulta sem filtro produz uma lista vazia. A criação de uma nova
partida, em contraste, é recusada com `503` enquanto não houver temporada
ativa.

### Limitações atuais

- Não existe ranking oficial do Nem a Pato; seu placar pertence à própria
  partida e permanece separado do Quiz Clássico.
- Não há paginação por cursor ou offset: a API retorna apenas os primeiros
  `limit` registros.
- Não há soma de pontos entre partidas, ranking acumulado entre temporadas ou
  fusão automática de uma identidade visitante com uma conta.
- Existe uma primitiva transacional interna para uma futura virada de
  temporada, mas não há endpoint público nem comando CLI para ativá-la.
- O endpoint não devolve a identidade interna do usuário ou visitante e não
  oferece busca por jogador.

### Nem a Pato

- Salas por código para 3 a 6 participantes ativos.
- Partidas com 10 rodadas e perguntas de resposta numérica.
- Palpites inteiros, não negativos e estritamente crescentes.
- Turnos circulares, desafio ao último palpite, penalização por “patos” e
  placar compartilhado.
- Timer autoritativo de 120 segundos por rodada, com tratamento de timeout com
  e sem palpites.
- Finalização, classificação, empates, cancelamento por jogadores
  insuficientes e revanche na mesma sala.
- Polling HTTP para sincronização; não há WebSocket no fluxo atual.
- Recuperação após atualização da página por credencial específica do
  participante, armazenada localmente pelo navegador.
- Idempotência de palpites e desafios por `client_action_id` e proteção
  transacional para operações concorrentes.
- Catálogo oficial e, quando a sala pertence a um usuário autenticado,
  conteúdo privado autorizado desse usuário.

### Autenticação e Meu Conteúdo

- Cadastro, login, consulta da sessão e logout.
- Senhas armazenadas com o mecanismo recomendado do `pwdlib` (Argon2 na
  instalação atual).
- Sessão JWT de 8 horas em cookie `HttpOnly`, `SameSite=Lax`; a opção
  `Secure` é configurável por ambiente.
- Perfis explícitos `JOGADOR` e `ADMIN`; novos cadastros recebem somente
  `JOGADOR`. O painel `/admin` e os endpoints administrativos validam o perfil
  no backend e retornam `401` sem sessão ou `403` sem permissão.
- Categorias privadas separadas entre Quiz Clássico e Nem a Pato.
- CRUD de categorias e perguntas próprias, com exclusão lógica.
- Limites implementados de 10 categorias e 200 perguntas por usuário e por
  modo.
- Importação privada de XLSX, CSV e JSON em duas etapas: prévia e confirmação.
- Prévia limitada a 5 MiB e 100 registros; o token de confirmação expira em
  15 minutos e o backend revalida arquivo, propriedade e quota.
- Gerador de prompts para uma IA externa. O QuizHub apenas monta e copia as
  instruções; não chama nem valida factualmente um serviço de IA. O prompt
  solicita um arquivo JSON compatível com o importador e prevê saída textual
  como alternativa quando a ferramenta externa não puder anexar arquivos.

## Arquitetura

```text
Navegador
   │
   │ HTTP/HTTPS + JSON (e multipart nas importações)
   ▼
React 19 + Vite 8
   │
   ▼
FastAPI + SQLAlchemy
   │
   ▼
PostgreSQL
```

- O frontend usa `VITE_API_URL` quando ela contém uma URL HTTP(S) válida. Sem
  essa variável, builds de produção usam a mesma origem da página (adequada a
  proxy reverso), enquanto o servidor de desenvolvimento usa
  `http://127.0.0.1:8001`.
- A API expõe `/health`, `/docs` e rotas sob `/api/v1`.
- O backend carrega `backend/.env` sem sobrescrever variáveis já definidas no
  ambiente do processo.
- O Nem a Pato mantém salas, participantes, partidas, rodadas, palpites e
  desafios no PostgreSQL. O frontend sincroniza o estado por polling.
- As partidas materializam snapshots das perguntas para preservar o conteúdo
  histórico mesmo após mudanças no catálogo.

## Tecnologias principais

| Camada | Tecnologia |
| --- | --- |
| Frontend | React 19, JavaScript, Vite 8 |
| API | Python, FastAPI, Uvicorn |
| Persistência | PostgreSQL, SQLAlchemy 2, psycopg 3 |
| Migrações | Alembic |
| Autenticação | PyJWT, `pwdlib[argon2]`, cookie HttpOnly |
| Arquivos | openpyxl, CSV e JSON da biblioteca padrão |
| Testes | `node:test` no frontend; `unittest` no backend |

As versões Python exatas estão fixadas em `backend/requirements.txt`; as
versões JavaScript ficam em `package.json` e `package-lock.json`.

## Estrutura do projeto

```text
quizhub/
├── compose.yaml                 # ambiente local completo da equipe
├── Dockerfile                   # frontend de desenvolvimento
├── backend/
│   ├── Dockerfile               # API e inicialização local
│   ├── alembic/                 # migrations incrementais (0001 a 0018)
│   ├── app/
│   │   ├── api/v1/              # endpoints HTTP
│   │   ├── cli/                 # comandos administrativos
│   │   ├── db/                  # sessão e seed de demonstração
│   │   ├── models/              # modelos SQLAlchemy
│   │   ├── schemas/             # contratos Pydantic
│   │   └── services/            # regras de negócio
│   ├── dados_oficiais/          # catálogos oficiais canônicos e manifesto
│   ├── tests/                   # testes unitários e de integração
│   ├── .env.example
│   ├── alembic.ini
│   └── requirements.txt
├── public/
├── src/
│   ├── components/
│   ├── hooks/
│   ├── services/
│   └── utils/
├── tests/                       # testes do frontend
├── package.json
├── package-lock.json
├── vite.config.js
└── README.md
```

## Como executar o QuizHub localmente — Guia da equipe

O caminho recomendado para uma instalação nova usa Docker Compose. Ele cria
um PostgreSQL exclusivo, aplica as migrations até `0019`, prepara e ativa os
dois catálogos canônicos versionados e inicia API e frontend. Nenhum acesso a
banco ou arquivo privado é necessário.

### Pré-requisitos

- Git;
- Docker Engine com o plugin Docker Compose;
- portas locais 5173, 8001 e 5433 livres (ou valores alternativos no `.env`).

### Primeira instalação

```bash
git clone https://github.com/Levibdo/quizhub.git
cd quizhub
cp .env.example .env
```

O `.env` da raiz contém somente configurações do Compose local. Antes de
subir o ambiente, substitua `POSTGRES_PASSWORD` e `JWT_SECRET` por valores
locais próprios; não versione esse arquivo.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Na primeira inicialização, o backend:

1. aguarda o PostgreSQL ficar saudável;
2. executa `alembic upgrade 0019`;
3. valida, importa e ativa idempotentemente os catálogos canônicos;
4. inicia o Uvicorn na porta interna 8001.

O bootstrap possui duas travas: precisa das flags locais definidas pelo
Compose e recusa bancos cujo nome não comece com `quizhub_local`. Ele não deve
ser reutilizado como procedimento de produção.

Endereços padrão:

- aplicação: `http://localhost:5173`;
- API: `http://localhost:8001`;
- saúde: `http://localhost:8001/health`;
- documentação HTTP: `http://localhost:8001/docs`;
- PostgreSQL no host: `localhost:5433`.

### Contas locais

Jogadores podem usar **Criar conta** na interface. Não existe senha, usuário
ou administrador padrão. Para criar o primeiro ADMIN no banco local, execute
o comando abaixo e informe uma senha de teste de forma interativa:

```bash
docker compose exec backend \
  python -m app.cli admin criar-inicial \
  --nome "Administrador local" --email admin@example.test
```

O comando é recusado se já houver um ADMIN. Nunca use nesse ambiente uma
senha real de outro serviço.

### Dados disponíveis para testes

O ambiente carrega a cópia versionada e homologada dos catálogos oficiais:

- 400 perguntas do Quiz Clássico;
- 100 perguntas do Nem a Pato;
- suas 506 referências editoriais.

Esses JSONs ficam em `backend/dados_oficiais/`; a inicialização não depende
de planilhas ou arquivos privados. Ranking e histórico começam vazios e só
recebem as partidas realizadas no banco local. **Meu Conteúdo** pode ser
testado com a conta criada pelo próprio colega e arquivos sintéticos nos
formatos documentados nesta página.

### Parar, reiniciar e redefinir

```bash
# parar sem perder o banco local
docker compose stop

# reiniciar o mesmo ambiente
docker compose start

# remover contêineres e rede, preservando o volume do banco
docker compose down

# acompanhar os logs
docker compose logs -f backend frontend
```

Para apagar **somente os dados locais deste Compose** e recomeçar, confirme
antes que o projeto exibido por `docker compose ls` é `quizhub-local` e use:

```bash
docker compose down --volumes
docker compose up --build -d
```

### Atualizar o código

Com o workspace sem alterações locais que precisem ser preservadas:

```bash
git pull --ff-only
docker compose up --build -d
```

As migrations e o bootstrap idempotente rodam novamente. O volume local é
mantido.

### Solução de problemas

- **Porta ocupada:** altere `FRONTEND_PORT`, `BACKEND_PORT` ou
  `POSTGRES_PORT` no `.env` e recrie os contêineres.
- **Backend não fica saudável:** consulte `docker compose logs backend` e
  `docker compose logs database`; confira se as credenciais do `.env` foram
  alteradas depois que o volume foi criado.
- **Credenciais do banco divergiram:** restaure os valores anteriores ou,
  somente se os dados locais puderem ser descartados, redefina o volume pelo
  procedimento acima.
- **Login funciona em uma origem e falha em outra:** use consistentemente
  `localhost` ou `127.0.0.1`; cookies pertencem ao host usado pelo navegador.
- **Build desatualizado:** execute `docker compose up --build -d`.
- **Verificação do schema:** `docker compose exec backend python -m alembic current`.

O fluxo manual sem Docker continua documentado abaixo para desenvolvimento
avancçado.

## Pré-requisitos

- Git.
- Python compatível com as dependências fixadas em
  `backend/requirements.txt`.
- Node.js compatível com a versão instalada do Vite 8 e npm.
- PostgreSQL acessível e um banco vazio criado para o ambiente.

O repositório não fixa uma versão de Python ou Node em arquivos como
`.python-version`, `.nvmrc` ou no campo `engines`. Se uma dependência recusar a
versão local, siga o requisito informado pelo próprio gerenciador.

## Configuração do ambiente

O arquivo de referência é `backend/.env.example`:

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Conexão SQLAlchemy com PostgreSQL. |
| `JWT_SECRET` | Segredo forte usado nos tokens de sessão e nas prévias de importação. |
| `JWT_COOKIE_SECURE` | Use `true` quando a aplicação for servida por HTTPS. |
| `CORS_ORIGINS` | Lista opcional, separada por vírgulas, de origens adicionais. |
| `VITE_API_URL` | URL base da API, definida no ambiente do frontend. |

Exemplo de formato, com valores fictícios:

```dotenv
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@localhost:5432/NOME_DO_BANCO
JWT_SECRET=SUBSTITUA_POR_UM_SEGREDO_ALEATORIO_FORTE
JWT_COOKIE_SECURE=false
CORS_ORIGINS=
```

Não versione `.env`, senhas ou tokens. `JWT_SECRET` é necessário para login e
para a importação privada. Em produção HTTPS, configure
`JWT_COOKIE_SECURE=true`.

## Instalação e execução local

### Linux

```bash
git clone https://github.com/Levibdo/quizhub.git
cd quizhub/backend

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cp .env.example .env
# Edite .env localmente, crie o banco PostgreSQL e só então aplique as migrations.
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Em outro terminal:

```bash
cd quizhub
npm ci
npm run dev
```

### macOS

Depois de instalar Git, Python, Node.js/npm e PostgreSQL pelo método de sua
preferência, os comandos são os mesmos do Linux:

```bash
git clone https://github.com/Levibdo/quizhub.git
cd quizhub/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Em outro terminal, na raiz do repositório:

```bash
npm ci
npm run dev
```

### Windows (PowerShell)

```powershell
git clone https://github.com/Levibdo/quizhub.git
cd quizhub\backend

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Copy-Item .env.example .env
# Edite .env localmente, crie o banco PostgreSQL e só então aplique as migrations.
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Em outro PowerShell:

```powershell
cd quizhub
npm ci
npm run dev
```

Se a política do PowerShell impedir a ativação do ambiente virtual, use o
executável do ambiente diretamente, sem alterar a política global:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### Endereços locais

- Frontend Vite: normalmente `http://localhost:5173`.
- API: `http://127.0.0.1:8001`.
- Saúde: `http://127.0.0.1:8001/health`.
- OpenAPI/Swagger: `http://127.0.0.1:8001/docs`.

Para usar outra URL da API:

```bash
# Linux/macOS
VITE_API_URL=http://127.0.0.1:8001 npm run dev
```

```powershell
# Windows PowerShell
$env:VITE_API_URL = "http://127.0.0.1:8001"
npm run dev
```

Como o frontend envia cookies com `credentials: include`, a origem usada pelo
navegador precisa estar permitida pelo CORS. Para origens adicionais às
aceitas no desenvolvimento, configure `CORS_ORIGINS` no backend.

## Banco de dados e migrations

A partir de `backend/`, com `DATABASE_URL` apontando para o banco correto:

```bash
python -m alembic current
python -m alembic heads
python -m alembic upgrade head
python -m alembic check
```

O head versionado é `0019` (`0019_operacoes_administrativas_idempotentes`). Antes de aplicar
migrations:

1. confira host e nome do banco;
2. faça backup quando houver dados relevantes;
3. não use um banco de produção em testes de integração;
4. não execute downgrade sem revisar a migration e o conteúdo existente.

As migrations `0001` a `0019` formam uma única cadeia incremental:

| Intervalo | Responsabilidade principal |
| --- | --- |
| `0001`–`0004` | Infraestrutura inicial, categorias, perguntas, jogadores, partidas, respostas e snapshots. |
| `0005`–`0008` | Usuários, autenticação, explicações obrigatórias e categorias oficiais básicas. |
| `0009`–`0010` | Fundação do Nem a Pato e desafios persistentes. |
| `0011` | Conteúdo privado de usuários e snapshots imutáveis. |
| `0012` | Identidade pseudônima `visitante_id` para o ranking. |
| `0013` | Temporadas, backfill histórico e associação das partidas. |
| `0014`–`0015` | Metadados editoriais, fontes e catálogos oficiais versionados. |
| `0016`–`0017` | Categoria oficial Macabro e metadados editoriais completos do Nem a Pato. |
| `0018` | Perfis `JOGADOR`/`ADMIN` e auditoria administrativa. |
| `0019` | Registros persistentes de idempotência para futuras operações administrativas sensíveis. |

As migrations criam e evoluem a estrutura, fazem os backfills declarados e
garantem categorias fundamentais. Os catálogos canônicos não são carregados
automaticamente apenas por executar `alembic upgrade head`; validação,
importação e ativação são operações distintas e controladas.

### Seed opcional de demonstração

```bash
cd backend
python -m app.db.seed
```

O seed é idempotente e adiciona categorias oficiais ausentes do Quiz Clássico
e 15 perguntas demonstrativas. Ele não alimenta o Nem a Pato e não deve ser
tratado como catálogo de produção.

## Administração dos catálogos

Execute os comandos dentro de `backend`, com o ambiente virtual ativo e a
conexão explicitamente conferida.

### Primeiro administrador

Depois de aplicar a migration `0018`, crie o primeiro administrador por um
terminal confiável. O comando solicita e confirma a senha sem gravá-la em
argumentos, arquivos ou histórico do shell, exige ao menos 12 caracteres e é
recusado quando já existe um perfil `ADMIN`:

```bash
python -m app.cli admin criar-inicial --nome "Administrador" --email admin@example.com
```

Não há credencial administrativa padrão nem promoção automática de usuários.
Confirme sempre o `DATABASE_URL` de destino antes de executar o bootstrap.

### Categorias oficiais e prompt administrativo

```bash
python -m app.cli categoria listar
python -m app.cli categoria criar
python -m app.cli prompt gerar
```

O gerador do CLI monta texto para uma ferramenta de IA externa; ele não envia
requisições a essa ferramenta nem importa automaticamente a resposta.

### Quiz Clássico

```bash
python -m app.cli perguntas validar caminho/perguntas.xlsx
python -m app.cli perguntas importar caminho/perguntas.xlsx

python -m app.cli perguntas validar caminho/perguntas.csv
python -m app.cli perguntas importar caminho/perguntas.csv

python -m app.cli perguntas validar caminho/perguntas.json
python -m app.cli perguntas importar caminho/perguntas.json
```

XLSX e CSV usam as colunas:

```text
categoria_id,enunciado,alternativa_a,alternativa_b,alternativa_c,alternativa_d,alternativa_correta,explicacao
```

`alternativa_correta` é um índice entre `0` (A) e `3` (D). O CSV usa vírgula e
UTF-8 (com ou sem BOM). O JSON aceito pelo importador tem esta estrutura:

```json
{
  "modo": "quiz_classico",
  "categoria_id": "geral",
  "perguntas": [
    {
      "enunciado": "Pergunta?",
      "alternativas": ["A", "B", "C", "D"],
      "alternativa_correta": 0,
      "explicacao": "Explicação da resposta."
    }
  ]
}
```

O endpoint legado `POST /api/v1/perguntas/importar` aceita XLSX, exige sessão
com perfil `ADMIN` e registra o resultado na auditoria administrativa.

### Nem a Pato

```bash
python -m app.cli nem-pato perguntas validar caminho/perguntas.xlsx
python -m app.cli nem-pato perguntas importar caminho/perguntas.xlsx
python -m app.cli nem-pato perguntas listar
python -m app.cli nem-pato perguntas resumo
python -m app.cli nem-pato perguntas criar
```

O validador e o importador também aceitam CSV e JSON. Os campos são:

```text
categoria_id,enunciado,resposta_numerica,explicacao,unidade,fonte,ativa
```

- Obrigatórios: `categoria_id`, `enunciado`, `resposta_numerica` e
  `explicacao`.
- Opcionais: `unidade`, `fonte` e `ativa`.
- `resposta_numerica` deve ser um inteiro entre `0` e
  `9223372036854775807`.
- XLSX não deve usar fórmula nesse campo e está sujeito à precisão inteira do
  formato; para inteiros muito grandes, prefira JSON ou CSV.
- O JSON desse modo é um array de objetos na raiz.

Os catálogos oficiais canônicos ficam em `backend/dados_oficiais/`:

- `quiz_classico_v2.json`: 400 perguntas, distribuídas entre quatro
  categorias oficiais;
- `nem_a_pato_macabro_v1.json`: 100 perguntas numéricas da categoria
  Macabro;
- `manifest.json`: associa cada arquivo ao `catalogo_id`, versão de schema,
  SHA-256 e estado editorial `PRONTO`.

O manifesto indica que o arquivo foi homologado para o fluxo editorial; ele
não prova, isoladamente, que uma versão esteja importada ou ativa em um banco.
Não adicione planilhas pessoais, exportações, rascunhos ou conteúdo privado ao
diretório canônico.

## API resumida

Todas as rotas abaixo ficam sob `/api/v1`:

| Área | Rotas principais |
| --- | --- |
| Autenticação | `/auth/cadastro`, `/auth/login`, `/auth/logout`, `/auth/me` |
| Categorias | `/categorias`, `/categorias/jogaveis` |
| Quiz Clássico | `/partidas`, `/partidas/{id}/respostas`, `/partidas/{id}/proxima` |
| Nem a Pato | `/nem-pato/salas/...` |
| Meu Conteúdo | `/meu-conteudo/resumo`, categorias, perguntas e importações |
| Administração | `/admin/resumo` (perfil `ADMIN`; catálogos e auditorias recentes) |
| Importação legada | `/perguntas/importar` (perfil `ADMIN`) |
| Ranking | `/ranking` (público; aceita `categoria`, `temporada` e `limit`), `/ranking/temporadas` |

Consulte `/docs` para os payloads exatos e os códigos de resposta.

## Testes e qualidade

### Frontend

Na raiz do repositório:

```bash
npm test
npm run lint
npm run build
```

- `npm test` executa `node --test tests/*.test.js`.
- `npm run build` gera o frontend em `dist/`.
- `npm run preview` serve o build apenas para inspeção local; não é uma
  recomendação de servidor de produção.

### Backend

Dentro de `backend/`, com o ambiente virtual ativo:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Os testes de integração em `backend/tests/integration/` possuem variáveis e
proteções próprias para bancos PostgreSQL descartáveis, por exemplo
`NEM_A_PATO_TEST_DATABASE_URL` nos cenários multiplayer e
`RANKING_TEST_DATABASE_URL`/`RANKING_TEST_DATABASE_NAME` no ranking real.

Antes de executar uma integração PostgreSQL:

- abra o arquivo do teste e confira as variáveis exigidas;
- use somente um banco temporário com o padrão de nome aceito pelo teste;
- confirme que a URL não aponta para desenvolvimento ou produção;
- considere que a suíte pode criar, esvaziar ou reconstruir dados/schema no
  banco autorizado.

Não há `pytest` em `backend/requirements.txt`; instalar ou documentar pytest
não é necessário para a suíte atual.

## Build e implantação

Gere o frontend estático com:

```bash
npm ci
npm run build
```

Os Dockerfiles e o Compose versionados destinam-se ao desenvolvimento local
da equipe. Eles não substituem configuração de Caddy/Nginx, unidade systemd ou
outros controles necessários a uma implantação de produção.

Requisitos mínimos para produção:

- servir `dist/` por um servidor HTTP de produção;
- encaminhar rotas da API ao Uvicorn executado sem `--reload`;
- configurar fallback da SPA para `index.html` nas rotas do frontend e deep
  links do Nem a Pato;
- usar HTTPS e `JWT_COOKIE_SECURE=true`;
- configurar `VITE_API_URL` no build ou usar proxy reverso coerente com a URL
  pública;
- permitir no CORS somente as origens necessárias quando frontend e API forem
  de origens diferentes;
- manter PostgreSQL fora da exposição pública e realizar backups;
- executar Uvicorn por um gerenciador de processos com reinício e logs;
- dimensionar workers, pool de conexões e recursos com medições do ambiente,
  não com números copiados de outra máquina.

Exemplo genérico, sem assumir gerenciador de processos ou quantidade de
workers:

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Um proxy reverso pode encaminhar `/api/`, `/health` e `/docs` para a API. Se a
API ficar em outro domínio, ajuste `VITE_API_URL`, cookies, HTTPS e CORS como
um conjunto. Tailscale Funnel, Caddy e Nginx são opções de infraestrutura, não
dependências do código versionado.

Quando frontend e API compartilham a mesma origem pública, o build de produção
pode omitir `VITE_API_URL` e usará `window.location.origin`. Se a API estiver
em outra origem, informe-a explicitamente durante o build:

```bash
VITE_API_URL=https://api.exemplo.invalid npm run build
```

Antes do deploy, confira o JavaScript gerado para garantir que nenhuma porta
exclusiva de desenvolvimento foi incluída:

```bash
if rg -n ":8001" dist/assets/*.js; then
  echo "ERRO: bundle de produção contém a porta de desenvolvimento"
  exit 1
fi
```

Quando uma API externa tiver sido configurada, confirme também sua origem com
`rg -n "https://api\.exemplo\.invalid" dist/assets/*.js`. No modo same-origin,
a origem é obtida de `window.location.origin` em tempo de execução e não precisa
aparecer como domínio literal no arquivo gerado.

Uma `VITE_API_URL` inválida, com protocolo diferente de HTTP(S), credenciais,
consulta ou fragmento interrompe a inicialização em vez de selecionar outro
servidor silenciosamente.

## Segurança e privacidade

- Nunca versione `.env`, segredos JWT, credenciais PostgreSQL ou tokens de
  participantes.
- Use um `JWT_SECRET` aleatório, longo e exclusivo por ambiente.
- Ative o cookie `Secure` somente junto de HTTPS e mantenha o cookie HttpOnly.
- Restrinja CORS; `allow_credentials` está ativo porque o frontend usa cookie
  de sessão.
- A credencial do Nem a Pato fica no `localStorage` para recuperação da sala.
  Evite scripts de terceiros e trate qualquer XSS como comprometimento dessa
  credencial.
- A identidade pseudônima de visitante e as credenciais de sala pertencem ao
  perfil do navegador; limpar o armazenamento local gera uma nova identidade
  para partidas futuras e remove as credenciais locais.
- A chave legada `quizhub-ranking` pode permanecer no navegador por
  compatibilidade, mas não é usada como fonte do ranking global.
- Valide arquivos antes de importar e revise a confirmação. A prévia privada
  não substitui as validações definitivas do backend.
- Não exponha diretamente PostgreSQL nem execute testes destrutivos em bancos
  com dados reais.

## Solução de problemas

### A API não conecta ao PostgreSQL

1. confira se PostgreSQL está ativo;
2. confira host, porta, usuário e nome do banco em `DATABASE_URL`;
3. execute `python -m alembic current` dentro de `backend/`;
4. não publique a URL completa em logs ou chamados, pois ela pode conter uma
   senha.

### Login retorna erro sobre `JWT_SECRET`

Copie `backend/.env.example` para `backend/.env` e defina um segredo forte.
Reinicie o processo do backend depois da alteração.

### O frontend não alcança a API

- confira `/health` diretamente;
- confira `VITE_API_URL` e se ela possui protocolo correto;
- lembre que variáveis `VITE_*` são incorporadas ao iniciar/buildar o
  frontend;
- se o navegador reportar CORS, adicione a origem exata a `CORS_ORIGINS` em
  vez de desativar a proteção.

### Cookie de login não é enviado

- em HTTP local, mantenha `JWT_COOKIE_SECURE=false`;
- em produção, use HTTPS e `JWT_COOKIE_SECURE=true`;
- confira domínio, origem, proxy e CORS;
- não tente resolver o problema expondo o token ao JavaScript.

### Uma categoria não inicia partida

Ela precisa estar ativa, não excluída, pertencer ao modo escolhido e possuir
pelo menos 10 perguntas elegíveis. Conteúdo privado só pode ser usado pelo seu
proprietário autenticado.

### Deep link da SPA retorna 404 em produção

Configure o servidor dos arquivos estáticos para entregar `index.html` nas
rotas de frontend que não correspondam a um arquivo. Não encaminhe por engano
as rotas `/api/` para a SPA.

### PowerShell bloqueia a ativação do venv

Execute o Python do ambiente virtual diretamente, como mostrado na instalação
Windows, sem mudar a política global da máquina.

## Estado e limites conhecidos

- Visitantes são agrupados no ranking pelo UUID guardado no perfil atual do
  navegador; navegadores ou perfis diferentes permanecem identidades distintas.
- O multiplayer usa polling HTTP; frequência e capacidade devem ser validadas
  no ambiente de implantação.
- A saúde em `/health` confirma que o processo responde, mas não executa uma
  verificação profunda do PostgreSQL.
- Operações administrativas feitas pela API exigem perfil `ADMIN`; os comandos
  locais continuam destinados apenas a operadores com acesso ao ambiente e ao
  banco explicitamente configurado.
- O endpoint legado `POST /api/v1/perguntas/importar` não possui uma chave ou
  autenticação exclusiva do importador, mas também não é anônimo: ele reutiliza
  obrigatoriamente a sessão por cookie e a autorização `ADMIN`. Aceita apenas
  XLSX, altera perguntas oficiais e registra sucesso ou rejeição na auditoria.
  Por continuar sendo uma superfície de escrita legada, deve permanecer atrás
  de HTTPS, cookie seguro e controle estrito das contas administrativas; não
  substitui o fluxo versionado dos catálogos oficiais.
- Não há configuração de infraestrutura de produção versionada.
- Compatibilidade visual e de teclado em navegadores/dispositivos específicos
  ainda exige validação no ambiente alvo.

## Licença

Não há arquivo de licença versionado no repositório. Antes de redistribuir ou
publicar o projeto sob uma licença específica, defina e adicione o documento
correspondente.
