const CHAVE_RANKING = 'quizhub-ranking'

export function carregarRanking() {
  const dados = localStorage.getItem(CHAVE_RANKING)

  if (!dados) {
    return []
  }

  try {
    return JSON.parse(dados)
  } catch {
    return []
  }
}

export function salvarResultado(resultado) {
  const rankingAtual = carregarRanking()

  const novoRanking = [
    ...rankingAtual,
    resultado,
  ]

  localStorage.setItem(
    CHAVE_RANKING,
    JSON.stringify(novoRanking)
  )
}