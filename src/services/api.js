const apiUrlConfigurada = import.meta.env?.VITE_API_URL?.trim()

const API_URL = (
  apiUrlConfigurada ||
  `${window.location.protocol}//${window.location.hostname}:8001`
).replace(/\/$/, '')

export async function requisitar(caminho, opcoes) {
  const corpoEhFormData = typeof FormData !== 'undefined' && opcoes?.body instanceof FormData
  let resposta
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      ...opcoes,
      credentials: 'include',
      headers: {
        ...(corpoEhFormData ? {} : { 'Content-Type': 'application/json' }),
        ...opcoes?.headers,
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

  return resposta.status === 204 ? null : resposta.json()
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
