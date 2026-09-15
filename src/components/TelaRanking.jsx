import { categorias } from '../data/categorias'

function TelaRanking({
  ranking,
  escolherCategoria,
  trocarJogador,
}) {
  const rankingOrdenado = [...ranking].sort(
    (a, b) => b.pontuacao - a.pontuacao
  )

  function nomeCategoria(id) {
    const categoria = categorias.find(
      (item) => item.id === id
    )

    return categoria?.nome ?? id
  }

  return (
    <>
      <h1>Ranking</h1>

      {rankingOrdenado.length === 0 ? (
        <p>Ainda não existem resultados.</p>
      ) : (
        <div className="ranking">
          {rankingOrdenado.map((resultado, indice) => (
            <div
              className="ranking-item"
              key={`${resultado.id}-${indice}`}
            >
              <span className="ranking-posicao">
                {indice + 1}º
              </span>

              <div className="ranking-jogador">
                <strong>{resultado.jogador}</strong>

                <small>
                  {nomeCategoria(resultado.categoria)}
                </small>
              </div>

              <strong>
                {resultado.pontuacao} pts
              </strong>
            </div>
          ))}
        </div>
      )}

      <div className="ranking-acoes">
        <button onClick={escolherCategoria}>
          Jogar novamente
        </button>

        <button onClick={trocarJogador}>
          Trocar jogador
        </button>
      </div>
    </>
  )
}

export default TelaRanking