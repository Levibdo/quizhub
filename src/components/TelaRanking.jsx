import { useState } from 'react'
import { classificarRanking } from '../utils/ranking'

function TelaRanking({
  ranking,
  categorias,
  carregandoCategorias,
  erroCategorias,
  tentarNovamente,
  voltarInicio,
  trocarJogador,
}) {
  const [filtroCategoria, setFiltroCategoria] = useState(null)
  const rankingOrdenado = classificarRanking(ranking, filtroCategoria)

  function chaveCategoria(categoria) {
    return categoria.origem === 'USUARIO'
      ? `privada:${categoria.id}`
      : categoria.slug
  }

  function nomeCategoria(chave) {
    return categorias.find((categoria) => chaveCategoria(categoria) === chave)?.nome ?? chave
  }

  const filtroAtual = filtroCategoria === null
    ? 'Todos'
    : nomeCategoria(filtroCategoria)

  return (
    <main className="ranking-screen">
      <header className="ranking-header">
        <p className="ranking-header__eyebrow">QuizHub // Classificação</p>
        <h1>Ranking</h1>
        <p>Os melhores resultados registrados neste dispositivo.</p>
      </header>

      <div className="ranking-filtros" aria-label="Filtrar ranking por categoria">
        <button
          className={filtroCategoria === null ? 'filtro-ativo' : ''}
          aria-pressed={filtroCategoria === null}
          onClick={() => setFiltroCategoria(null)}
        >
          Todos
        </button>
        {categorias.map((categoria) => (
          <button
            key={categoria.id}
            className={filtroCategoria === chaveCategoria(categoria) ? 'filtro-ativo' : ''}
            aria-pressed={filtroCategoria === chaveCategoria(categoria)}
            onClick={() => setFiltroCategoria(chaveCategoria(categoria))}
          >
            {categoria.nome}
          </button>
        ))}
      </div>

      {carregandoCategorias && (
        <p className="ranking-categories-state" role="status">Carregando categorias...</p>
      )}
      {!carregandoCategorias && erroCategorias && (
        <div className="ranking-categories-state ranking-categories-state--error" role="alert">
          <span>{erroCategorias}</span>
          <button className="button-link" onClick={tentarNovamente}>Tentar novamente</button>
        </div>
      )}
      {!carregandoCategorias && !erroCategorias && categorias.length === 0 && (
        <p className="ranking-categories-state">Nenhuma categoria disponível para filtro.</p>
      )}

      {rankingOrdenado.length === 0 ? (
        <section className="ranking-empty">
          <span className="ranking-empty__signal" aria-hidden="true" />
          <h2>Ranking vazio</h2>
          <p>
            {filtroCategoria === null
              ? 'Ainda não existem resultados registrados neste dispositivo.'
              : `Ainda não existem resultados em ${filtroAtual}.`}
          </p>
        </section>
      ) : (
        <ol className="ranking" aria-label={`Classificação: ${filtroAtual}`}>
          {rankingOrdenado.map((resultado, indice) => (
            <li className="ranking-item" key={resultado.id}>
              <span className="ranking-posicao" aria-label={`${indice + 1}ª posição`}>
                {String(indice + 1).padStart(2, '0')}
              </span>
              <div className="ranking-jogador">
                <strong>{resultado.jogador}</strong>
                <small>{resultado.acertos} acertos · {nomeCategoria(resultado.categoria)}</small>
              </div>
              <strong className="ranking-pontos">
                {new Intl.NumberFormat('pt-BR').format(resultado.pontuacao)} <small>pts</small>
              </strong>
            </li>
          ))}
        </ol>
      )}

      <div className="ranking-acoes">
        <button className="ranking-acoes__primary" onClick={trocarJogador}>
          Jogar novamente →
        </button>
        <button className="button-ghost" onClick={voltarInicio}>
          Voltar ao início
        </button>
      </div>
    </main>
  )
}

export default TelaRanking
