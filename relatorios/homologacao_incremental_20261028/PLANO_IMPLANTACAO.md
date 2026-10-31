# Plano controlado de implantação

Este documento é um procedimento proposto. Nenhum comando abaixo foi
executado em produção durante a consolidação.

## 1. Inventário e preflight

1. Fixar o commit autorizado e registrar `git status --short`, `git log` e os
   hashes dos artefatos.
2. Confirmar que a release contém backend, migration `0022`, frontend e testes
   homologados, sem `.env`, credenciais, rascunhos ou XLSX protegido.
3. Consultar, somente em leitura, o banco e registrar a revisão Alembic real.
   A publicação incremental depende da cadeia linear `0019 → 0020 → 0021
   → 0022`; se o destino não estiver na revisão expressamente homologada no
   ensaio de restauração, interromper. Confirmar que o destino é exatamente o
   banco autorizado.
4. Confirmar saúde da API, frontend atual, espaço em disco e procedimento de
   controle do serviço.

Critério de interrupção: qualquer divergência de commit, banco, revisão,
artefato ou permissão.

## 2. Backup verificável

Com variáveis preenchidas interativamente no ambiente autorizado:

```bash
install -d -m 700 "$BACKUP_DIR"
pg_dump --format=custom --file="$BACKUP_DIR/database.dump" "$DATABASE_URL"
tar --acls --xattrs --numeric-owner -czf "$BACKUP_DIR/backend.tar.gz" -C /opt quizhub/backend
tar --acls --xattrs --numeric-owner -czf "$BACKUP_DIR/frontend.tar.gz" -C /var/www quizhub
sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/SHA256SUMS"
sha256sum --check "$BACKUP_DIR/SHA256SUMS"
pg_restore --list "$BACKUP_DIR/database.dump" >/dev/null
```

Restaurar o dump em PostgreSQL 16 descartável, aplicar nele a cadeia completa
até `0022`, executar consultas de contagem independentes e exigir
correspondência antes de continuar. O backup deve ficar fora dos diretóios
servidos.

Critério de interrupção: dump vazio, hash divergente ou restauração falha.

## 3. Migrations 0020 a 0022

Usar a release imutável e o ambiente Python de produção:

```bash
cd "$RELEASE_DIR/backend"
"$PROD_VENV/bin/alembic" -c alembic.ini current
"$PROD_VENV/bin/alembic" -c alembic.ini heads
"$PROD_VENV/bin/alembic" -c alembic.ini history -r 0019:0022
"$PROD_VENV/bin/alembic" -c alembic.ini upgrade 0022
"$PROD_VENV/bin/alembic" -c alembic.ini current
```

`upgrade 0022` aplica sequencialmente as estruturas de rascunhos (`0020`),
revisão e aprovação (`0021`) e o vínculo de publicação (`0022`). Exigir head
único `0022`, todas as tabelas esperadas, as duas colunas anuláveis da `0022`,
FK `RESTRICT`, unicidade e check constraint. Confirmar contagens históricas
inalteradas.

## 4. Backend

1. Preparar a release em diretório separado.
2. Comparar dependências e validar imports antes da interrupção.
3. Preservar `.env`, `.venv`, proprietário e permissões.
4. Parar o serviço, trocar somente os arquivos versionados do backend e iniciar
   o serviço.
5. Exigir serviço ativo, `/health` 200, endpoints públicos esperados e ausência
   de traceback/HTTP 500 nos logs.

Critério de rollback de código: API não inicia ou smoke test crítico falha.
A migration `0022` é aditiva; o rollback de schema não substitui restauração
do backup.

## 5. Frontend

1. Construir com a URL de API autorizada e verificar ausência de `localhost`.
2. Publicar assets versionados antes do HTML.
3. Validar hashes e HTTP 200 dos novos assets.
4. Trocar `index.html` por renomeação atômica no mesmo filesystem.

## 6. Testes de fumaça

- `/health` e rotas públicas respondem conforme contrato.
- visitante recebe 401 e JOGADOR 403 em administração.
- ADMIN acessa a consulta administrativa.
- catálogos e versões existentes permanecem visíveis.
- criar rascunho, editar, revisar e publicar somente em ambiente de homologação;
  em produção, evitar escrita no smoke test inicial.
- Quiz Clássico, Nem a Pato, ranking e autenticação carregam sem erros JS/500.

Aceite: todos os checks críticos aprovados, Alembic `0022`, contagens
históricas preservadas e nenhum erro relevante nos logs.

## 7. Recuperação

1. Interromper novas mudanças e registrar o estado real.
2. Se o defeito for apenas frontend, restaurar atomicamente o `index.html`
   anterior e manter os assets antigos.
3. Se o backend falhar, restaurar o código anterior e reiniciar o serviço;
   `0022` é compatível com linhas legadas.
4. Se houver corrupção ou perda de dados, isolar a aplicação e restaurar o
   dump validado. Não executar downgrade automático como substituto.
5. Revalidar saúde, revisão, contagens e logs, e emitir relatório de incidente.
