import { useState } from 'react'
import { categorias } from '../data/categorias'

function TelaRanking({
  ranking,
  voltarInicio,
  trocarJogador,
}) {
  const [filtroCategoria, setFiltroCategoria] =
    useState('geral-ranking')

  function nomeCategoria(id) {
    const categoria = categorias.find(
      (item) => item.id === id
    )

    return categoria?.nome ?? id
  }

  const resultadosFiltrados =
    filtroCategoria === 'geral-ranking'
      ? ranking
      : ranking.filter(
          (resultado) =>
            resultado.categoria === filtroCategoria
        )

  const melhoresPorJogador = Object.values(
    resultadosFiltrados.reduce(
      (melhores, resultado) => {
        const resultadoAtual =
          melhores[resultado.jogador]

        if (
          !resultadoAtual ||
          resultado.pontuacao >
            resultadoAtual.pontuacao ||
          (resultado.pontuacao ===
            resultadoAtual.pontuacao &&
            resultado.acertos >
              resultadoAtual.acertos) ||
          (resultado.pontuacao ===
            resultadoAtual.pontuacao &&
            resultado.acertos ===
              resultadoAtual.acertos &&
            resultado.id < resultadoAtual.id)
        ) {
          melhores[resultado.jogador] = resultado
        }

        return melhores
      },
      {}
    )
  )

  const rankingOrdenado = melhoresPorJogador
    .sort((a, b) => {
      if (b.pontuacao !== a.pontuacao) {
        return b.pontuacao - a.pontuacao
      }

      if (b.acertos !== a.acertos) {
        return b.acertos - a.acertos
      }

      return a.id - b.id
    })
    .slice(0, 10)

  return (
    <>
      <h1>Ranking</h1>

      <div className="ranking-filtros">
        <button
          className={
            filtroCategoria === 'geral-ranking'
              ? 'filtro-ativo'
              : ''
          }
          onClick={() =>
            setFiltroCategoria('geral-ranking')
          }
        >
          Geral
        </button>

        {categorias.map((categoria) => (
          <button
            key={categoria.id}
            className={
              filtroCategoria === categoria.id
                ? 'filtro-ativo'
                : ''
            }
            onClick={() =>
              setFiltroCategoria(categoria.id)
            }
          >
            {categoria.nome}
          </button>
        ))}
      </div>

      {rankingOrdenado.length === 0 ? (
        <p>
          Ainda não existem resultados para este
          ranking.
        </p>
      ) : (
        <div className="ranking">
          {rankingOrdenado.map(
            (resultado, indice) => (
              <div
                className="ranking-item"
                key={resultado.id}
              >
                <span className="ranking-posicao">
                  {indice + 1}º
                </span>

                <div className="ranking-jogador">
                  <strong>
                    {resultado.jogador}
                  </strong>

                  <small>
                    {nomeCategoria(
                      resultado.categoria
                    )}
                  </small>
                </div>

                <div className="ranking-pontos">
                  <strong>
                    {resultado.pontuacao} pts
                  </strong>

                  <small>
                    {resultado.acertos} acertos
                  </small>
                </div>
              </div>
            )
          )}
        </div>
      )}

      <div className="ranking-acoes">
        <button onClick={voltarInicio}>
          Início
        </button>

        <button onClick={trocarJogador}>
          Jogar
        </button>
      </div>
    </>
  )
}

export default TelaRanking