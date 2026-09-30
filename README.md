# QuizHub

O QuizHub é uma aplicação web de quiz desenvolvida inicialmente como projeto acadêmico. O jogo oferece partidas de múltipla escolha organizadas por categoria, tempo por pergunta, pontuação e ranking.

## Funcionalidades

- Identificação do jogador por nome ou apelido.
- Escolha entre as categorias Geral, Tecnologia e Matemática.
- Catálogo atual com 105 perguntas, sendo 35 por categoria.
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

O diretório `backend/dados/` armazena as planilhas usadas para carregar e expandir o catálogo. O seed do backend inclui 15 perguntas, com 5 por categoria. Cada uma das duas planilhas possui outras 45 perguntas, com 15 por categoria e sem sobreposição. Após executar o seed e importar ambas, o catálogo totaliza 105 perguntas, sendo 35 por categoria.

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
python -m app.db.seed
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

No Linux ou macOS, ative o ambiente virtual com `source .venv/bin/activate` e defina a conexão com:

```bash
export DATABASE_URL="postgresql+psycopg://USUARIO:SENHA@localhost:5432/quiz_estagio_db"
```

O seed é idempotente e cadastra as três categorias e as 15 perguntas-base que ainda não existirem.

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

Para validar o frontend, execute na raiz do projeto:

```powershell
npm run lint
npm run build
```

## Acesso em rede

O backend e o frontend podem escutar em `0.0.0.0`, permitindo acesso por outros dispositivos da rede. O frontend deve ser iniciado com `npm run dev -- --host 0.0.0.0`, e o backend com a opção `--host 0.0.0.0` mostrada anteriormente.

Para cenários em que a API esteja em outro host ou porta, configure `VITE_API_URL`. O backend aceita origens de desenvolvimento na porta `5173`, e origens adicionais podem ser informadas pela variável `CORS_ORIGINS`, separadas por vírgula.

## Estado atual

O MVP possui backend persistente, motor autoritativo de partidas, catálogo com 105 perguntas em três categorias, partidas de 10 perguntas, frontend funcional e ranking local no navegador.

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
