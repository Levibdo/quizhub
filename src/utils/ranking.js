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

export function classificarRanking(ranking, categoria = null) {
  const resultados = categoria === null
    ? ranking
    : ranking.filter((resultado) => resultado.categoria === categoria)

  const melhoresPorJogador = resultados.reduce((melhores, resultado) => {
    const atual = melhores.get(resultado.jogador)

    if (
      !atual ||
      resultado.pontuacao > atual.pontuacao ||
      (resultado.pontuacao === atual.pontuacao && resultado.acertos > atual.acertos) ||
      (resultado.pontuacao === atual.pontuacao && resultado.acertos === atual.acertos && resultado.id < atual.id)
    ) {
      melhores.set(resultado.jogador, resultado)
    }

    return melhores
  }, new Map())

  return [...melhoresPorJogador.values()]
    .sort((a, b) => {
      if (b.pontuacao !== a.pontuacao) return b.pontuacao - a.pontuacao
      if (b.acertos !== a.acertos) return b.acertos - a.acertos
      return a.id - b.id
    })
    .slice(0, 10)
}
