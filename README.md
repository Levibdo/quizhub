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
├── backend/
│   ├── alembic/                 # migrations 0001 a 0011
│   ├── app/
│   │   ├── api/v1/              # endpoints HTTP
│   │   ├── cli/                 # comandos administrativos
│   │   ├── db/                  # sessão e seed de demonstração
│   │   ├── models/              # modelos SQLAlchemy
│   │   ├── schemas/             # contratos Pydantic
│   │   └── services/            # regras de negócio
│   ├── dados/                   # catálogos versionados
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

O head versionado é `0011` (`0011_fundacao_conteudo_usuario`). Antes de aplicar
migrations:

1. confira host e nome do banco;
2. faça backup quando houver dados relevantes;
3. não use um banco de produção em testes de integração;
4. não execute downgrade sem revisar a migration e o conteúdo existente.

As migrations criam a estrutura e as categorias oficiais de ambos os modos.
Elas não carregam automaticamente todos os catálogos de perguntas.

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

O endpoint legado `POST /api/v1/perguntas/importar` aceita XLSX. Ele não exige
autenticação no código atual; em uma implantação pública, restrinja esse
endpoint no proxy/rede ou prefira uma rotina administrativa controlada.

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

Os arquivos em `backend/dados/` são catálogos versionados. Não adicione
planilhas pessoais, exportações ou arquivos com conteúdo privado sem uma
decisão explícita de versionamento.

## API resumida

Todas as rotas abaixo ficam sob `/api/v1`:

| Área | Rotas principais |
| --- | --- |
| Autenticação | `/auth/cadastro`, `/auth/login`, `/auth/logout`, `/auth/me` |
| Categorias | `/categorias`, `/categorias/jogaveis` |
| Quiz Clássico | `/partidas`, `/partidas/{id}/respostas`, `/partidas/{id}/proxima` |
| Nem a Pato | `/nem-pato/salas/...` |
| Meu Conteúdo | `/meu-conteudo/resumo`, categorias, perguntas e importações |
| Importação legada | `/perguntas/importar` |
| Ranking | `/ranking` (público; aceita `categoria` e `limit`) |

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
`NEM_A_PATO_TEST_DATABASE_URL` nos cenários multiplayer.

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

O repositório não inclui Dockerfile, Compose, configuração de Caddy/Nginx ou
unidade systemd. Uma implantação de produção precisa definir esses elementos
fora do projeto ou adicioná-los em uma etapa própria.

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
- O endpoint legado de importação XLSX não possui autenticação própria.
- Não há configuração de infraestrutura de produção versionada.
- Compatibilidade visual e de teclado em navegadores/dispositivos específicos
  ainda exige validação no ambiente alvo.

## Licença

Não há arquivo de licença versionado no repositório. Antes de redistribuir ou
publicar o projeto sob uma licença específica, defina e adicione o documento
correspondente.
