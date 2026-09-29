const apiUrlConfigurada = import.meta.env.VITE_API_URL?.trim()

const API_URL = (
  apiUrlConfigurada ||
  `${window.location.protocol}//${window.location.hostname}:8001`
).replace(/\/$/, '')

async function requisitar(caminho, opcoes) {
  let resposta
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      ...opcoes,
      headers: { 'Content-Type': 'application/json', ...opcoes?.headers },
    })
  } catch {
    throw new Error('Não foi possível conectar ao servidor.')
  }

  if (!resposta.ok) {
    let mensagem = 'O servidor não conseguiu concluir a operação.'
    try {
      const corpo = await resposta.json()
      if (typeof corpo.detail === 'string') mensagem = corpo.detail
    } catch {
      // Mantém a mensagem genérica quando a resposta não é JSON.
    }
    throw new Error(mensagem)
  }

  return resposta.json()
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
