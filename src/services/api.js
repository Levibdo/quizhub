function normalizarUrlHttp(valor, origem) {
  let url
  try {
    url = new URL(valor, origem)
  } catch {
    throw new TypeError('VITE_API_URL deve ser uma URL HTTP(S) válida')
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new TypeError('VITE_API_URL deve ser uma URL HTTP(S) válida, sem credenciais, consulta ou fragmento')
  }
  return url.href.replace(/\/$/, '')
}

export function resolverApiUrl({ configurada, producao = false, origem, desenvolvimento } = {}) {
  const valorConfigurado = configurada?.trim()
  if (valorConfigurado) return normalizarUrlHttp(valorConfigurado)
  if (producao) {
    if (!origem) throw new TypeError('A origem do frontend é obrigatória no build de produção')
    return normalizarUrlHttp(origem)
  }
  if (!desenvolvimento) throw new TypeError('A URL da API de desenvolvimento é obrigatória')
  return normalizarUrlHttp(desenvolvimento)
}

const API_URL = resolverApiUrl({
  configurada: import.meta.env?.VITE_API_URL,
  producao: import.meta.env?.PROD === true,
  origem: globalThis.window?.location?.origin,
  desenvolvimento: import.meta.env?.PROD === true ? undefined : 'http://127.0.0.1:8001',
})

function exigeCsrfAdministrativo(caminho, metodo) {
  const escrita = !['GET', 'HEAD', 'OPTIONS'].includes(metodo.toUpperCase())
  return escrita && (
    caminho.startsWith('/api/v1/admin/') ||
    caminho === '/api/v1/perguntas/importar'
  )
}

export async function requisitar(caminho, opcoes) {
  const { preservarBigInt = false, ...opcoesFetch } = opcoes ?? {}
  const metodo = opcoesFetch.method ?? 'GET'
  const corpoEhFormData = typeof FormData !== 'undefined' && opcoesFetch.body instanceof FormData
  let tokenCsrf
  if (exigeCsrfAdministrativo(caminho, metodo)) {
    const emissao = await requisitar('/api/v1/admin/csrf', { method: 'GET' })
    tokenCsrf = emissao.token
  }
  let resposta
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      ...opcoesFetch,
      credentials: 'include',
      headers: {
        ...(corpoEhFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(tokenCsrf ? { 'X-CSRF-Token': tokenCsrf } : {}),
        ...opcoesFetch.headers,
      },
    })
  } catch {
    throw new Error('Não foi possível conectar ao servidor.')
  }

  if (!resposta.ok) {
    let mensagem = 'O servidor não conseguiu concluir a operação.'
    let erroDetalhes
    try {
      const corpo = await resposta.json()
      if (typeof corpo.detail === 'string') mensagem = corpo.detail
      if (corpo.detail && typeof corpo.detail === 'object' && !Array.isArray(corpo.detail)) {
        if (typeof corpo.detail.mensagem === 'string') mensagem = corpo.detail.mensagem
      }
      if (Array.isArray(corpo.detail)) {
        const mensagens = {
          nome: 'Informe um nome válido (até 100 caracteres).',
          email: 'Informe um e-mail válido.',
          senha: 'Verifique a senha informada (cadastro: 8 a 128 caracteres).',
        }
        mensagem = [...new Set(corpo.detail.map((item) =>
          mensagens[item.loc?.at(-1)] || 'Verifique os campos informados.',
        ))].join(' ')
      }
      erroDetalhes = corpo.detail
    } catch {
      // Mantém a mensagem genérica quando a resposta não é JSON.
    }
    const erro = new Error(mensagem)
    erro.status = resposta.status
    erro.detail = erroDetalhes
    erro.codigo = erroDetalhes?.codigo
    throw erro
  }

  if (resposta.status === 204) return null
  if (preservarBigInt) {
    const texto = await resposta.text()
    return JSON.parse(texto.replace(
      /("resposta_numerica"\s*:\s*)(\d+)/g,
      (_trecho, prefixo, numero) => `${prefixo}"${numero}"`,
    ))
  }
  return resposta.json()
}

export function obterResumoMeuConteudo() {
  return requisitar('/api/v1/meu-conteudo/resumo', { method: 'GET' })
}

export function listarCategoriasMeuConteudo(modo) {
  const parametros = new URLSearchParams({ modo })
  return requisitar(`/api/v1/meu-conteudo/categorias?${parametros}`, { method: 'GET' })
}

export function criarCategoriaMeuConteudo(dados) {
  return requisitar('/api/v1/meu-conteudo/categorias', {
    method: 'POST', body: JSON.stringify(dados),
  })
}

export function editarCategoriaMeuConteudo(categoriaId, dados) {
  return requisitar(`/api/v1/meu-conteudo/categorias/${categoriaId}`, {
    method: 'PATCH', body: JSON.stringify(dados),
  })
}

export function excluirCategoriaMeuConteudo(categoriaId) {
  return requisitar(`/api/v1/meu-conteudo/categorias/${categoriaId}`, { method: 'DELETE' })
}

function caminhoPerguntasMeuConteudo(modo) {
  return modo === 'QUIZ_CLASSICO' ? 'classico' : 'nem-a-pato'
}

const RESPOSTA_NUMERICA_MAXIMA = '9223372036854775807'

function serializarPerguntaNemPato(dados) {
  if (!Object.hasOwn(dados, 'resposta_numerica')) return JSON.stringify(dados)
  const informado = String(dados.resposta_numerica)
  if (!/^\d+$/.test(informado)) throw new TypeError('resposta_numerica deve ser um inteiro não negativo')
  const numero = informado.replace(/^0+(?=\d)/, '')
  if (numero.length > RESPOSTA_NUMERICA_MAXIMA.length ||
      (numero.length === RESPOSTA_NUMERICA_MAXIMA.length && numero > RESPOSTA_NUMERICA_MAXIMA)) {
    throw new RangeError(`resposta_numerica deve ser no máximo ${RESPOSTA_NUMERICA_MAXIMA}`)
  }
  return `{${Object.entries(dados).map(([campo, valor]) => (
    `${JSON.stringify(campo)}:${campo === 'resposta_numerica' ? numero : JSON.stringify(valor)}`
  )).join(',')}}`
}

export function listarPerguntasMeuConteudo(modo, filtros = {}) {
  const parametros = new URLSearchParams()
  if (filtros.categoria_id) parametros.set('categoria_id', filtros.categoria_id)
  if (filtros.ativa !== '' && filtros.ativa !== undefined) parametros.set('ativa', String(filtros.ativa))
  parametros.set('offset', String(filtros.offset ?? 0))
  parametros.set('limit', String(filtros.limit ?? 20))
  return requisitar(`/api/v1/meu-conteudo/perguntas/${caminhoPerguntasMeuConteudo(modo)}?${parametros}`, {
    method: 'GET', preservarBigInt: modo === 'NEM_A_PATO',
  })
}

export function obterPerguntaMeuConteudo(modo, perguntaId) {
  return requisitar(`/api/v1/meu-conteudo/perguntas/${caminhoPerguntasMeuConteudo(modo)}/${perguntaId}`, {
    method: 'GET', preservarBigInt: modo === 'NEM_A_PATO',
  })
}

export function criarPerguntaMeuConteudo(modo, dados) {
  return requisitar(`/api/v1/meu-conteudo/perguntas/${caminhoPerguntasMeuConteudo(modo)}`, {
    method: 'POST', body: modo === 'NEM_A_PATO' ? serializarPerguntaNemPato(dados) : JSON.stringify(dados),
    preservarBigInt: modo === 'NEM_A_PATO',
  })
}

export function editarPerguntaMeuConteudo(modo, perguntaId, dados) {
  return requisitar(`/api/v1/meu-conteudo/perguntas/${caminhoPerguntasMeuConteudo(modo)}/${perguntaId}`, {
    method: 'PATCH', body: modo === 'NEM_A_PATO' ? serializarPerguntaNemPato(dados) : JSON.stringify(dados),
    preservarBigInt: modo === 'NEM_A_PATO',
  })
}

export function excluirPerguntaMeuConteudo(modo, perguntaId) {
  return requisitar(`/api/v1/meu-conteudo/perguntas/${caminhoPerguntasMeuConteudo(modo)}/${perguntaId}`, { method: 'DELETE' })
}

export function validarImportacaoMeuConteudo(modo, arquivo) {
  const formulario = new FormData()
  formulario.append('modo', modo)
  formulario.append('arquivo', arquivo)
  return requisitar('/api/v1/meu-conteudo/importacoes/validar', {
    method: 'POST', body: formulario,
  })
}

export function confirmarImportacaoMeuConteudo(tokenPreview, arquivo) {
  const formulario = new FormData()
  formulario.append('token_preview', tokenPreview)
  formulario.append('arquivo', arquivo)
  return requisitar('/api/v1/meu-conteudo/importacoes/confirmar', {
    method: 'POST', body: formulario,
  })
}

export function cadastrarUsuario(nome, email, senha) {
  return requisitar('/api/v1/auth/cadastro', {
    method: 'POST', body: JSON.stringify({ nome, email, senha }),
  })
}

export function login(email, senha) {
  return requisitar('/api/v1/auth/login', {
    method: 'POST', body: JSON.stringify({ email, senha }),
  })
}

export function logout() {
  return requisitar('/api/v1/auth/logout', { method: 'POST' })
}

export function obterUsuarioAtual() {
  return requisitar('/api/v1/auth/me', { method: 'GET' })
}

export function obterResumoAdministrativo() {
  return requisitar('/api/v1/admin/resumo', { method: 'GET' })
}

export function obterDashboardAdministrativo() {
  return requisitar('/api/v1/admin/dashboard', { method: 'GET' })
}

export function listarCatalogosOficiaisAdministrativos() {
  return requisitar('/api/v1/admin/catalogos', { method: 'GET' })
}

export function criarCatalogoInicialOficial(dados, chave) {
  return requisitar('/api/v1/admin/catalogos', {
    method: 'POST', headers: { 'Idempotency-Key': chave || chaveIdempotencia() },
    body: JSON.stringify(dados),
  })
}

export function reativarCatalogoOficial(id, justificativa, catalogoAtivoId, chave) {
  return requisitar(`/api/v1/admin/catalogos/${id}/reativar`, {
    method: 'POST',
    headers: {
      'If-Match': `"${catalogoAtivoId}"`,
      'Idempotency-Key': chave || chaveIdempotencia(),
    },
    body: JSON.stringify({ justificativa }),
  })
}

function chaveIdempotencia() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `quizhub-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function cabecalhosEscritaRascunho(revisao, chave) {
  return {
    ...(revisao === undefined ? {} : { 'If-Match': `"${revisao}"` }),
    'Idempotency-Key': chave || chaveIdempotencia(),
  }
}

function cabecalhosRevisaoEditorial(revisaoConteudo, revisaoEditorial, chave) {
  return {
    ...cabecalhosEscritaRascunho(revisaoConteudo, chave),
    ...(revisaoEditorial === undefined || revisaoEditorial === null
      ? {}
      : { 'X-Editorial-Revision': String(revisaoEditorial) }),
  }
}

export function listarRascunhosOficiais(filtros = {}) {
  const parametros = new URLSearchParams()
  for (const [campo, valor] of Object.entries(filtros)) {
    if (valor !== '' && valor !== null && valor !== undefined) parametros.set(campo, String(valor))
  }
  return requisitar(`/api/v1/admin/catalogos/rascunhos?${parametros}`, { method: 'GET' })
}

export function obterRascunhoOficial(id) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${id}`, { method: 'GET' })
}

export function validarRascunhoOficial(id) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${id}/validacao`, { method: 'GET' })
}

export function criarRascunhoOficial(catalogoId, nome, chave) {
  return requisitar(`/api/v1/admin/catalogos/${catalogoId}/rascunhos`, {
    method: 'POST', headers: cabecalhosEscritaRascunho(undefined, chave),
    body: JSON.stringify({ nome }),
  })
}

export function listarPerguntasRascunho(rascunhoId, filtros = {}) {
  const parametros = new URLSearchParams()
  for (const [campo, valor] of Object.entries(filtros)) {
    if (valor !== '' && valor !== null && valor !== undefined) parametros.set(campo, String(valor))
  }
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/perguntas?${parametros}`, { method: 'GET' })
}

export function listarCategoriasRascunho(rascunhoId) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/categorias`, { method: 'GET' })
}

export function salvarCategoriaRascunho(rascunhoId, categoriaId, dados, revisao, chave) {
  const sufixo = categoriaId ? `/${categoriaId}` : ''
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/categorias${sufixo}`, {
    method: categoriaId ? 'PUT' : 'POST', headers: cabecalhosEscritaRascunho(revisao, chave),
    body: JSON.stringify(dados),
  })
}

export function removerCategoriaRascunho(rascunhoId, categoriaId, revisao, chave) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/categorias/${categoriaId}`, {
    method: 'DELETE', headers: cabecalhosEscritaRascunho(revisao, chave),
  })
}

export function restaurarCategoriaRascunho(rascunhoId, categoriaId, revisao, chave) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/categorias/${categoriaId}/restaurar`, {
    method: 'POST', headers: cabecalhosEscritaRascunho(revisao, chave),
  })
}

export function previsualizarImportacaoCatalogoJson(catalogoId, conteudo) {
  return requisitar(`/api/v1/admin/catalogos/${catalogoId}/importacoes/json/previsualizar`, {
    method: 'POST', body: JSON.stringify(conteudo),
  })
}

export function confirmarImportacaoCatalogoJson(catalogoId, conteudo, sha256Esperado, chave) {
  return requisitar(`/api/v1/admin/catalogos/${catalogoId}/importacoes/json/confirmar`, {
    method: 'POST', headers: cabecalhosEscritaRascunho(undefined, chave),
    body: JSON.stringify({ sha256_esperado: sha256Esperado, conteudo }),
  })
}

export function obterPerguntaRascunho(rascunhoId, perguntaId) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/perguntas/${perguntaId}`, { method: 'GET' })
}

export function salvarPerguntaRascunho(rascunhoId, perguntaId, dados, revisao, chave) {
  const sufixo = perguntaId ? `/${perguntaId}` : ''
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/perguntas${sufixo}`, {
    method: perguntaId ? 'PUT' : 'POST', headers: cabecalhosEscritaRascunho(revisao, chave),
    body: JSON.stringify(dados),
  })
}

export function removerPerguntaRascunho(rascunhoId, perguntaId, revisao, chave) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/perguntas/${perguntaId}`, {
    method: 'DELETE', headers: cabecalhosEscritaRascunho(revisao, chave),
  })
}

export function restaurarPerguntaRascunho(rascunhoId, perguntaId, revisao, chave) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/perguntas/${perguntaId}/restaurar`, {
    method: 'POST', headers: cabecalhosEscritaRascunho(revisao, chave),
  })
}

export function listarHistoricoRascunho(rascunhoId, pagina = 1) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/alteracoes?pagina=${pagina}&limite=20`, { method: 'GET' })
}

export function descartarRascunhoOficial(rascunhoId, motivo, revisao, chave) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/descartar`, {
    method: 'POST', headers: cabecalhosEscritaRascunho(revisao, chave),
    body: JSON.stringify({ motivo }),
  })
}

export function obterRevisaoRascunho(rascunhoId) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/revisao`, { method: 'GET' })
}

export function listarPerguntasRevisao(rascunhoId, filtros = {}) {
  const parametros = new URLSearchParams()
  for (const [campo, valor] of Object.entries(filtros)) {
    if (valor !== '' && valor !== null && valor !== undefined) parametros.set(campo, String(valor))
  }
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/revisao/perguntas?${parametros}`, { method: 'GET' })
}

export function listarAvisosRevisao(rascunhoId, filtros = {}) {
  const parametros = new URLSearchParams()
  for (const [campo, valor] of Object.entries(filtros)) {
    if (valor !== '' && valor !== null && valor !== undefined) parametros.set(campo, String(valor))
  }
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/revisao/avisos?${parametros}`, { method: 'GET' })
}

export function obterHistoricoRevisaoPergunta(rascunhoId, perguntaId) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}/revisao/perguntas/${perguntaId}/historico`, { method: 'GET' })
}

function escreverRevisao(rascunhoId, caminho, dados, revisaoConteudo, revisaoEditorial, chave) {
  return requisitar(`/api/v1/admin/catalogos/rascunhos/${rascunhoId}${caminho}`, {
    method: 'POST', headers: cabecalhosRevisaoEditorial(revisaoConteudo, revisaoEditorial, chave),
    body: JSON.stringify(dados ?? {}),
  })
}

export const encaminharRascunhoRevisao = (id, revisao, chave) => escreverRevisao(id, '/encaminhar-revisao', {}, revisao, undefined, chave)
export const decidirPerguntaRevisao = (id, perguntaId, dados, revisao, editorial, chave) => escreverRevisao(id, `/revisao/perguntas/${perguntaId}/decisoes`, dados, revisao, editorial, chave)
export const verificarFonteRevisao = (id, perguntaId, fonteId, dados, revisao, editorial, chave) => escreverRevisao(id, `/revisao/perguntas/${perguntaId}/fontes/${fonteId}/verificacoes`, dados, revisao, editorial, chave)
export const decidirAvisoRevisao = (id, achadoId, dados, revisao, editorial, chave) => escreverRevisao(id, `/revisao/avisos/${achadoId}/decisao`, dados, revisao, editorial, chave)
export const solicitarCorrecaoRascunho = (id, dados, revisao, editorial, chave) => escreverRevisao(id, '/solicitar-correcao', dados, revisao, editorial, chave)
export const devolverRascunhoEdicao = (id, dados, revisao, editorial, chave) => escreverRevisao(id, '/devolver-edicao', dados, revisao, editorial, chave)
export const aprovarRascunhoEditorial = (id, dados, revisao, editorial, chave) => escreverRevisao(id, '/aprovar', dados, revisao, editorial, chave)
export const reabrirRascunhoEditorial = (id, dados, revisao, chave) => escreverRevisao(id, '/reabrir', dados, revisao, undefined, chave)
export const publicarRascunhoEditorial = (id, justificativa, revisao, chave) => escreverRevisao(id, '/publicar', { justificativa }, revisao, undefined, chave)

export function obterOpcoesPerguntasOficiais() {
  return requisitar('/api/v1/admin/perguntas/opcoes', { method: 'GET' })
}

export function listarPerguntasOficiais(filtros = {}) {
  const parametros = new URLSearchParams()
  for (const [chave, valor] of Object.entries(filtros)) {
    if (valor !== '' && valor !== null && valor !== undefined) {
      parametros.set(chave, String(valor))
    }
  }
  return requisitar(`/api/v1/admin/perguntas?${parametros}`, { method: 'GET' })
}

export function obterPerguntaOficial(modo, id) {
  return requisitar(`/api/v1/admin/perguntas/${modo}/${id}`, { method: 'GET' })
}

export function listarAuditoriasAdministrativas(filtros = {}) {
  const parametros = new URLSearchParams()
  for (const [chave, valor] of Object.entries(filtros)) {
    if (valor !== '' && valor !== null && valor !== undefined) {
      parametros.set(chave, String(valor))
    }
  }
  return requisitar(`/api/v1/admin/auditorias?${parametros}`, { method: 'GET' })
}

export function importarPerguntasOficiaisLegado(arquivo) {
  const formulario = new FormData()
  formulario.append('arquivo', arquivo)
  return requisitar('/api/v1/perguntas/importar', {
    method: 'POST', body: formulario,
  })
}

export function listarCategorias() {
  return requisitar('/api/v1/categorias', { method: 'GET' })
}

export function listarCategoriasJogaveis() {
  return requisitar('/api/v1/categorias/jogaveis', { method: 'GET' })
}

export function criarPartida(jogador, categoria) {
  const dados = { jogador, categoria }
  return requisitar('/api/v1/partidas', {
    method: 'POST',
    body: JSON.stringify(dados),
  })
}

export function obterPartida(partidaId) {
  return requisitar(`/api/v1/partidas/${partidaId}`, { method: 'GET' })
}

export function listarRanking(categoria = null, limit = 10) {
  const parametros = new URLSearchParams({ limit: String(limit) })
  if (categoria) parametros.set('categoria', categoria)
  return requisitar(`/api/v1/ranking?${parametros}`, { method: 'GET' })
}

export function enviarResposta(partidaId, perguntaId, alternativa) {
  return requisitar(`/api/v1/partidas/${partidaId}/respostas`, {
    method: 'POST',
    body: JSON.stringify({ pergunta_id: perguntaId, alternativa }),
  })
}

export function avancarPergunta(partidaId, perguntaId) {
  return requisitar(`/api/v1/partidas/${partidaId}/proxima`, {
    method: 'POST',
    body: JSON.stringify({ pergunta_id: perguntaId }),
  })
}
