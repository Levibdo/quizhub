# QuizHub

O QuizHub é uma plataforma web de perguntas e jogos com dois modos: o **Quiz
Clássico**, individual, e o **Nem a Pato**, multiplayer. A aplicação também
oferece conteúdo privado para jogadores autenticados e um fluxo editorial
administrativo completo para catálogos oficiais.

> **Status:** versão definitiva implantada e em modo de manutenção desde
> **15/11/2026**.
> **Aplicação pública:** <https://quizhub.tailef8ba8.ts.net/>
> **Tag de produção:** `production/2026-11-15-final-74f4ae5`

## Sumário

- [Funcionalidades](#funcionalidades)
- [Arquitetura e tecnologias](#arquitetura-e-tecnologias)
- [Instalação com Docker Compose](#instalação-com-docker-compose)
- [Instalação manual](#instalação-manual)
- [Banco de dados e migrations](#banco-de-dados-e-migrations)
- [Administração de conteúdo](#administração-de-conteúdo)
- [API](#api)
- [Segurança](#segurança)
- [Manutenção operacional](#manutenção-operacional)
- [Testes e qualidade](#testes-e-qualidade)
- [Solução de problemas](#solução-de-problemas)
- [Produção e limitações](#produção-e-limitações)
- [Licença](#licença)

## Funcionalidades

### Quiz Clássico

- Partida individual com 10 perguntas sem repetição.
- Prazo de 15 segundos por pergunta. Cada acerto vale
  `100 + (segundos restantes × 10)`, entre 100 e 250 pontos; erro ou timeout
  vale zero. Uma partida pode chegar a 2.500 pontos.
- Seleção das perguntas, correção, prazo, pontuação e progressão controlados
  pelo backend.
- A resposta correta e a explicação só são reveladas depois da resposta ou do
  timeout.
- Recuperação da mesma partida após F5, fechamento da aba ou perda temporária
  de rede, preservando UUID, sequência, respostas e prazo original.
- Proteção contra respostas duplicadas e sincronização após conflitos de
  concorrência.
- Categorias oficiais e categorias privadas elegíveis do próprio jogador.
- Ranking público de partidas oficiais concluídas.

O ranking público usa a pontuação oficial persistida no PostgreSQL e considera
somente partidas oficiais `FINALIZADA`. Cada identidade aparece por sua melhor
partida. O desempate usa, nesta ordem, pontuação, acertos, conclusão mais antiga
e UUID da partida. Categorias privadas e partidas do Nem a Pato não entram
nesse ranking. Os filtros públicos aceitam categoria, temporada e limite.

### Nem a Pato

- Salas multiplayer por código para 3 a 6 participantes ativos, com entrada,
  lobby, início e abandono.
- Partidas de 10 rodadas com perguntas de resposta numérica.
- Palpites inteiros, não negativos e estritamente crescentes, turnos
  circulares, desafio ao último palpite e penalização por “patos”.
- Prazo autoritativo de 120 segundos por rodada, incluindo tratamento de
  timeout com ou sem palpites.
- Finalização, classificação, empates, cancelamento por jogadores insuficientes
  e opção de jogar novamente na mesma sala.
- Estado persistido no PostgreSQL e recuperação da participação do jogador.
- Perguntas oficiais elegíveis do modo `NEM_A_PATO`.

O multiplayer usa polling HTTP; não há transporte WebSocket implementado.

### Autenticação

- Cadastro, login, consulta da sessão e logout.
- Senhas protegidas com Argon2.
- Sessão por JWT em cookie `HttpOnly`, com `Secure` em produção e política
  `SameSite` configurada pelo backend.
- Perfis `JOGADOR` e `ADMIN`.
- Identidade visitante assinada para proteger a propriedade de partidas
  clássicas sem transformar um UUID público em credencial.

### Meu Conteúdo

A área autenticada possui cinco abas, na ordem mantida pela interface:

1. categorias;
2. perguntas;
3. meu ranking;
4. importar;
5. gerar prompt.

Ela permite:

- criar, editar e desativar categorias próprias;
- gerenciar perguntas próprias do Quiz Clássico e do Nem a Pato;
- importar conteúdo privado com pré-visualização e confirmação;
- gerar prompts auxiliares para preparação de conteúdo;
- consultar as melhores partidas concluídas do próprio usuário, agrupadas
  somente por categorias que ele criou.

A navegação é responsiva, possui semântica de abas e suporte a teclado. Na aba
**Perguntas**, nenhuma listagem é carregada na entrada: o usuário precisa
selecionar explicitamente um filtro, pesquisar ou escolher todas as categorias.
Limpar os filtros retorna ao estado inicial, que é diferente do estado de uma
busca sem resultados. Cadastro, edição, exclusão e paginação permanecem
disponíveis depois da consulta.

### Painel administrativo

O painel web para `ADMIN` inclui:

- resumo e dashboard;
- consulta de perguntas e catálogos oficiais;
- criação de catálogo e de rascunho versionado;
- categorias e perguntas versionadas dentro do rascunho;
- importação oficial **JSON** com pré-visualização, validação e confirmação;
- revisão por pergunta, verificação de fontes e decisões editoriais;
- solicitação de correção, retorno à edição, aprovação e reabertura;
- publicação incremental transacional;
- consulta do histórico e reativação segura de versões arquivadas;
- auditoria administrativa.

Importar não publica automaticamente. A publicação exige que o rascunho passe
pelos estados e validações editoriais correspondentes.

## Arquitetura e tecnologias

| Camada | Tecnologias principais |
| --- | --- |
| Frontend | React, Vite, JavaScript e CSS |
| API | Python, FastAPI e Pydantic |
| Persistência | PostgreSQL 16, SQLAlchemy e Alembic |
| Autenticação | JWT em cookie e Argon2 |
| Testes | Pytest, Vitest e Playwright nas homologações visuais |
| Ambiente local | Docker Compose |

O frontend consome a API sob `/api/v1`. O PostgreSQL é a fonte de verdade para
partidas, respostas, salas, conteúdo e rankings. Snapshots e vínculos
versionados preservam o significado histórico mesmo depois da evolução dos
catálogos.

## Instalação com Docker Compose

### Requisitos

- Docker com Compose v2;
- portas locais livres, por padrão `5433`, `8001` e `5173`.

### Configuração

Copie os exemplos e ajuste apenas valores locais:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

As variáveis mais relevantes são:

- raiz: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`;
- backend: `DATABASE_URL`, `JWT_SECRET`, `JWT_COOKIE_SECURE`,
  `CORS_ORIGINS` e `CSRF_TRUSTED_ORIGINS`;
- frontend: variáveis `VITE_*` existentes no build, quando necessárias.

Use um e-mail sintático válido ao cadastrar a primeira conta, por exemplo
`admin@example.com`. Nunca reutilize segredos de produção no ambiente local.

### Inicialização

```bash
docker compose up --build
```

O Compose publica as portas apenas no loopback e inicia os serviços nesta
dependência lógica:

1. PostgreSQL 16 fica saudável;
2. o serviço efêmero `migrate` aplica a revisão explícita `0023`;
3. o backend só inicia se o migrador terminar com sucesso;
4. o frontend inicia para desenvolvimento local.

O backend não executa migrations silenciosamente ao subir. Ele valida o schema
e, no modo local previsto pelo Compose, pode inicializar os catálogos canônicos
quando configurado. O runner de migrations usa advisory lock para serializar a
operação.

Endereços padrão:

- frontend: <http://127.0.0.1:5173>;
- API: <http://127.0.0.1:8001>;
- health: <http://127.0.0.1:8001/health>;
- PostgreSQL: `127.0.0.1:5433`.

Para acompanhar ou encerrar:

```bash
docker compose ps
docker compose logs -f backend migrate
docker compose down
```

Para atualizar uma instalação local, obtenha o código desejado e reconstrua:

```bash
docker compose up --build -d
```

Remover volumes apaga o banco. Faça isso somente em ambiente local descartável
e depois de conferir o projeto e os volumes selecionados:

```bash
docker compose down --volumes
```

Não use esse comando em uma instalação com dados que precisem ser preservados.

### Primeira conta administrativa

O cadastro público cria um `JOGADOR`. A promoção inicial para `ADMIN` é uma
operação controlada do operador, fora da interface pública. Faça-a apenas no
banco local explicitamente identificado e nunca documente ou compartilhe
credenciais. Contas administrativas subsequentes devem seguir o procedimento
operacional adotado para o ambiente.

## Instalação manual

### Linux

Requisitos: Python compatível com o projeto, Node.js/npm e PostgreSQL 16.

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Configure um PostgreSQL local cujo nome comece com `quizhub_local` e ajuste a
`DATABASE_URL`. O runner também exige o ambiente, modo e alvo explícitos:

```bash
export QUIZHUB_SCHEMA_REVISION=0023
export QUIZHUB_MIGRATION_MODE=local
export QUIZHUB_LOCAL_ENVIRONMENT=development
.venv/bin/python -m app.db.migrations migrate
```

Depois inicie a API:

```bash
.venv/bin/python -m app.db.migrations check
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Em outro terminal, a partir da raiz:

```bash
npm ci --include=optional
npm run dev
```

### macOS

Instale PostgreSQL 16, Python e Node.js por um gerenciador confiável. Os
comandos e variáveis são os mesmos do Linux. Em Macs com Apple Silicon, não copie um
virtualenv criado em outra arquitetura: recrie-o localmente.

### Windows (PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:QUIZHUB_SCHEMA_REVISION = "0023"
$env:QUIZHUB_MIGRATION_MODE = "local"
$env:QUIZHUB_LOCAL_ENVIRONMENT = "development"
.\.venv\Scripts\python.exe -m app.db.migrations migrate
.\.venv\Scripts\python.exe -m app.db.migrations check
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Em outro terminal, na raiz do projeto:

```powershell
npm ci --include=optional
npm run dev
```

Executar diretamente o Python do virtualenv evita alterar globalmente a
política de execução do PowerShell.

### Segurança das migrations

O alvo versionado é explicitamente `0023`. O modo local exige ambiente de
desenvolvimento e o prefixo de banco permitido pelo runner. O modo controlado
para banco persistente exige autorização operacional adicional. Configuração
ausente ou incompatível interrompe a inicialização; não existe fallback para
uma migration automática inesperada.

## Banco de dados e migrations

O repositório possui um único head Alembic: `0023`.

| Revisão | Alteração principal |
| --- | --- |
| `0001` | infraestrutura inicial |
| `0002` | categorias e perguntas |
| `0003` | jogadores e partidas |
| `0004` | perguntas e respostas das partidas |
| `0005` | usuários e vínculo com jogador |
| `0006` | explicação inicialmente opcional |
| `0007` | explicação obrigatória |
| `0008` | categorias oficiais básicas |
| `0009` | persistência do Nem a Pato |
| `0010` | resolução persistente de desafios |
| `0011` | conteúdo do usuário e snapshots imutáveis |
| `0012` | identidade pseudônima de visitante |
| `0013` | temporadas do ranking |
| `0014` | metadados editoriais opcionais |
| `0015` | catálogos oficiais versionados e proveniência |
| `0016` | categoria Macabro |
| `0017` | metadados editoriais do Nem a Pato |
| `0018` | perfil `ADMIN` e auditoria administrativa |
| `0019` | idempotência administrativa |
| `0020` | rascunhos oficiais |
| `0021` | revisão e aprovação editorial |
| `0022` | vínculo da publicação incremental |
| `0023` | categorias oficiais versionadas, snapshots históricos e proveniência legada |

A migration `0023` preserva perguntas oficiais históricas sem inventar
proveniência ausente. Conteúdo novo e versionado continua sujeito aos vínculos
completos e às constraints correspondentes. Não execute downgrade como
estratégia rotineira de rollback: para banco persistente, valide backup e
restauração antes da janela de mudança.

## Administração de conteúdo

Há três conjuntos distintos:

1. **catálogos canônicos no Git**: arquivos JSON e manifesto usados como fonte
   controlada de bootstrap e referência;
2. **conteúdo oficial no PostgreSQL**: versões, rascunhos, categorias,
   perguntas, fontes e estados editoriais efetivamente usados pela aplicação;
3. **conteúdo privado**: categorias e perguntas pertencentes ao usuário.

Os arquivos canônicos incluem `quiz_classico_v2.json`,
`nem_a_pato_macabro_v1.json` e `manifest.json`. Suas quantidades não devem ser
interpretadas como o total existente em uma produção específica.

### Importações

- **Privada:** a área Meu Conteúdo aceita XLSX, CSV e JSON em duas etapas:
  pré-visualização e confirmação. O backend limita o arquivo a 5 MiB e 100
  registros, aplica quotas, revalida o arquivo na confirmação e usa um token de
  prévia com validade limitada.
- **Oficial versionada:** o painel administrativo aceita JSON, preserva fontes
  estruturadas e cria conteúdo em rascunho; não publica automaticamente.
- **Legada:** `POST /api/v1/perguntas/importar` aceita XLSX sob sessão `ADMIN`.
  É uma superfície compatível com o fluxo anterior e não substitui o processo
  editorial versionado.

CSV/XLSX não são oferecidos pela interface como importação oficial versionada.

## API

Todas as rotas abaixo usam o prefixo `/api/v1`, salvo `/health`.

| Área | Métodos e caminhos principais | Acesso |
| --- | --- | --- |
| Saúde | `GET /health` | público |
| Autenticação | `POST /auth/cadastro`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | misto |
| Categorias | `GET /categorias`, `GET /categorias/jogaveis` | público/contextual |
| Quiz Clássico | `POST /partidas`, `GET /partidas/{id}`, `POST /partidas/{id}/respostas`, `POST /partidas/{id}/proxima` | proprietário autenticado ou visitante assinado |
| Ranking público | `GET /ranking`, `GET /ranking/temporadas` | público |
| Nem a Pato | `/nem-pato/salas` e operações de lobby, partida, rodada, palpite e desafio | participantes |
| Meu Conteúdo | `/meu-conteudo/resumo`, `/categorias`, perguntas e importações | `JOGADOR` autenticado |
| Ranking pessoal | `GET /meu-conteudo/ranking` | usuário autenticado; somente categorias e partidas próprias |
| Administração | `/admin/resumo`, `/dashboard`, `/catalogos`, `/perguntas`, `/auditorias` | `ADMIN` |
| Editorial | `/admin/catalogos/.../rascunhos`, importação JSON, revisão, aprovação, publicação e reativação | `ADMIN`, CSRF e controles de concorrência |

Consulte os schemas e routers versionados antes de automatizar integrações: os
campos obrigatórios, headers de concorrência e respostas de erro fazem parte do
contrato real.

## Segurança

- Senhas são derivadas com Argon2; não são armazenadas em texto puro.
- O JWT de sessão fica em cookie `HttpOnly`; em produção, o cookie deve ser
  `Secure` e servido exclusivamente por HTTPS.
- CORS usa lista de origens explícitas.
- Escritas clássicas validam `Origin`/`Referer`; origens públicas legítimas
  devem constar em `CSRF_TRUSTED_ORIGINS` quando necessário.
- Operações administrativas mutáveis exigem origem confiável e token CSRF
  vinculado à sessão.
- Endpoints sensíveis usam `Idempotency-Key`; alterações versionadas usam
  `If-Match` onde o contrato exige controle otimista.
- Autorização por propriedade é aplicada no backend para conteúdo privado e
  partidas, não apenas escondida no frontend.
- Publicação e reativação de catálogos são transacionais e auditadas.
- Snapshots preservam partidas e rankings históricos.
- O Compose local restringe PostgreSQL, backend e frontend ao loopback. Em
  outros ambientes, limite `listen_addresses`, HBA e firewall às origens
  realmente necessárias.

As dependências diretas estão registradas nos arquivos do projeto, mas isso
não significa que toda dependência transitiva esteja imutavelmente fixada em
todos os ambientes. Use instalação reproduzível do frontend e valide o
ambiente Python da release.

## Manutenção operacional

### Backup seguro do PostgreSQL

`backend/scripts/backup_postgres.py` interpreta a `DATABASE_URL` com
SQLAlchemy, valida driver/host/porta/banco, usa um `PGPASSFILE` temporário
protegido e chama `pg_dump` sem shell. O próprio utilitário exige que o dump
seja não vazio e legível por `pg_restore --list`.

Exemplo para um banco **local descartável**:

```bash
cd backend
.venv/bin/python scripts/backup_postgres.py \
  --env-file .env \
  --output ../backups/quizhub-local.dump \
  --expected-host 127.0.0.1 \
  --expected-port 5433 \
  --expected-database quizhub_local
sha256sum ../backups/quizhub-local.dump
pg_restore --list ../backups/quizhub-local.dump >/dev/null
```

Crie o diretório de destino com permissões restritas antes da execução. Uma
restauração deve ser ensaiada em PostgreSQL 16 descartável, nunca diretamente
sobre o banco de origem. Preserve o SHA-256 e compare contagens e integridade
antes e depois das migrations.

### Encerramento de partidas abandonadas

`backend/scripts/encerrar_partidas_abandonadas.py` é uma operação manual:

- dry-run é o padrão;
- a inatividade mínima aceita é 72 horas;
- execução exige IDs explícitos, confirmação do banco e justificativa;
- a transação revalida estado e atividade sob lock;
- respostas, participantes, rodadas, palpites, pontuações e rankings são
  preservados;
- não há expiração automática recorrente.

Dry-run seletivo:

```bash
cd backend
.venv/bin/python scripts/encerrar_partidas_abandonadas.py \
  --env-file .env \
  --classic-id UUID_DA_PARTIDA \
  --room-id UUID_DA_SALA \
  --min-inactivity-hours 72 \
  --report ../relatorios/encerramento-dry-run.json
```

Execução controlada, somente em janela autorizada:

```bash
.venv/bin/python scripts/encerrar_partidas_abandonadas.py \
  --env-file .env \
  --classic-id UUID_DA_PARTIDA \
  --room-id UUID_DA_SALA \
  --min-inactivity-hours 72 \
  --execute \
  --confirm-database NOME_EXATO_DO_BANCO \
  --justification "manutencao operacional autorizada" \
  --report ../relatorios/encerramento-executado.json
```

`--all-eligible` existe apenas para inventário em dry-run. Antes de qualquer
execução persistente, coloque a aplicação em manutenção, pare novas escritas,
gere e valide um backup e revise individualmente os IDs elegíveis.

## Testes e qualidade

### Backend

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/alembic heads
```

Testes que dependem de PostgreSQL devem usar uma instância PostgreSQL 16
descartável e uma URL de teste inequivocamente separada de qualquer banco
persistente.

### Frontend

Na raiz do projeto:

```bash
npm ci --include=optional
npm test
npm run lint
npm run build
```

Na homologação definitiva de **15/11/2026** foram registrados:

- backend: **488 testes aprovados**;
- frontend: **182 testes aprovados**;
- operação PostgreSQL: **4 testes aprovados**;
- ESLint aprovado;
- build Vite aprovado.

Esses totais são evidência daquela release, não uma contagem permanente para
commits futuros.

## Solução de problemas

### A API não conecta ao PostgreSQL

- confirme que o PostgreSQL 16 está saudável e que host, porta e banco da
  `DATABASE_URL` correspondem ao ambiente local;
- dentro do Compose, use o nome do serviço `database`, não `localhost`;
- confira os logs de `database`, `migrate` e `backend` sem imprimir a URL ou
  credenciais.

### A inicialização para na migration

- não substitua o alvo explícito por `head`;
- confira `QUIZHUB_SCHEMA_REVISION=0023`, o modo local, o ambiente
  `development` e o prefixo `quizhub_local` do banco;
- corrija a causa e execute novamente o serviço `migrate`; não altere
  manualmente `alembic_version`.

### Login informa que `JWT_SECRET` está ausente

Defina um segredo local forte no ambiente do backend. Não o inclua no Git, em
logs ou em comandos compartilhados.

### O frontend não alcança a API

- teste `/health` diretamente;
- confira `VITE_API_URL` antes de iniciar ou compilar o frontend, pois
  variáveis `VITE_*` são incorporadas ao build;
- se houver erro de CORS ou CSRF, cadastre a origem exata em `CORS_ORIGINS` e
  `CSRF_TRUSTED_ORIGINS`, sem desativar as proteções.

### O cookie de login não é enviado

Em HTTP local, use `JWT_COOKIE_SECURE=false`. Em produção, use HTTPS e
`JWT_COOKIE_SECURE=true`. Confira também origem, proxy, CORS e domínio; não
exponha o JWT ao JavaScript como solução alternativa.

### Uma categoria não inicia partida

A categoria precisa estar ativa, não excluída, pertencer ao modo escolhido e
ter pelo menos 10 perguntas elegíveis. Conteúdo privado só pode ser usado pelo
seu proprietário autenticado.

### Um deep link da SPA retorna 404

O servidor de arquivos estáticos deve entregar `index.html` para rotas do
frontend que não correspondam a arquivos. Rotas `/api/` devem continuar sendo
encaminhadas à API.

### PowerShell bloqueia a ativação do virtualenv

Execute o Python do ambiente virtual diretamente, como no exemplo Windows,
sem mudar a política global da máquina.

## Produção e limitações

Na implantação definitiva:

- backend ativo: `3c579ff93c8285cac4b19b297acbcfb9ed50ff46`;
- frontend e documentação final: `74f4ae54da5b47116b1ce62857555ec1b80b41aa`;
- schema: Alembic `0023`;
- tag: `production/2026-11-15-final-74f4ae5`.

A diferença entre os commits é intencional: o commit final consolida o
frontend e os artefatos documentais posteriores sem exigir uma troca
desnecessária do backend já homologado.

Limitações atuais:

- não há gestão avançada de usuários no painel;
- não há gestão avançada de temporadas;
- perguntas oficiais publicadas não são excluídas diretamente pela interface;
- a importação oficial versionada pela interface é JSON, não CSV/XLSX;
- não existe expiração recorrente automática de partidas abandonadas;
- o ranking oficial é do Quiz Clássico; o Nem a Pato não possui ranking oficial
  equivalente;
- o multiplayer usa polling;
- `/health` confirma o processo, mas não é um diagnóstico profundo de todas as
  dependências.

## Licença

Não há arquivo de licença versionado no repositório. Antes de redistribuir ou
publicar o projeto sob uma licença específica, defina e adicione o documento
correspondente.
