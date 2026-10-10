const apiUrlConfigurada = import.meta.env?.VITE_API_URL?.trim()

const API_URL = (
  apiUrlConfigurada ||
  `${window.location.protocol}//${window.location.hostname}:8001`
).replace(/\/$/, '')

export async function requisitar(caminho, opcoes) {
  const { preservarBigInt = false, ...opcoesFetch } = opcoes ?? {}
  const corpoEhFormData = typeof FormData !== 'undefined' && opcoesFetch.body instanceof FormData
  let resposta
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      ...opcoesFetch,
      credentials: 'include',
      headers: {
        ...(corpoEhFormData ? {} : { 'Content-Type': 'application/json' }),
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

export function listarCategorias() {
  return requisitar('/api/v1/categorias', { method: 'GET' })
}

export function listarCategoriasJogaveis() {
  return requisitar('/api/v1/categorias/jogaveis', { method: 'GET' })
}

export function criarPartida(jogador, categoria) {
  return requisitar('/api/v1/partidas', {
    method: 'POST',
    body: JSON.stringify({ jogador, categoria }),
  })
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
