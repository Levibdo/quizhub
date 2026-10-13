import { useEffect, useState } from 'react'
import { listarRanking } from '../services/api'

function TelaRanking({
  categorias,
  carregandoCategorias,
  erroCategorias,
  tentarNovamente,
  voltarInicio,
  trocarJogador,
}) {
  const [filtroCategoria, setFiltroCategoria] = useState(null)
  const [ranking, setRanking] = useState([])
  const [carregandoRanking, setCarregandoRanking] = useState(true)
  const [erroRanking, setErroRanking] = useState('')
  const [tentativaRanking, setTentativaRanking] = useState(0)

  useEffect(() => {
    let ativo = true
    listarRanking(filtroCategoria, 10).then((resultado) => {
      if (ativo) setRanking(resultado)
    }).catch((error) => {
      if (!ativo) return
      setRanking([])
      setErroRanking(`Não foi possível carregar o ranking global. ${error.message}`)
    }).finally(() => {
      if (ativo) setCarregandoRanking(false)
    })
    return () => { ativo = false }
  }, [filtroCategoria, tentativaRanking])

  function carregarComFiltro(novoFiltro) {
    setCarregandoRanking(true)
    setErroRanking('')
    setRanking([])
    if (novoFiltro === filtroCategoria) setTentativaRanking((valor) => valor + 1)
    else setFiltroCategoria(novoFiltro)
  }

  function tentarRankingNovamente() {
    setCarregandoRanking(true)
    setErroRanking('')
    setTentativaRanking((valor) => valor + 1)
  }

  function chaveCategoria(categoria) {
    return categoria.origem === 'USUARIO'
      ? `privada:${categoria.id}`
      : categoria.slug
  }

  function nomeCategoria(chave) {
    return categorias.find((categoria) => chaveCategoria(categoria) === chave)?.nome ?? chave
  }

  const categoriasPublicas = categorias.filter((categoria) => categoria.origem !== 'USUARIO')

  const filtroAtual = filtroCategoria === null
    ? 'Todos'
    : nomeCategoria(filtroCategoria)

  return (
    <main className="ranking-screen">
      <header className="ranking-header">
        <p className="ranking-header__eyebrow">QuizHub // Classificação</p>
        <h1>Ranking</h1>
        <p>Os melhores resultados oficiais do QuizHub.</p>
      </header>

      <div className="ranking-filtros" aria-label="Filtrar ranking por categoria">
        <button
          className={filtroCategoria === null ? 'filtro-ativo' : ''}
          aria-pressed={filtroCategoria === null}
          onClick={() => carregarComFiltro(null)}
        >
          Todos
        </button>
        {categoriasPublicas.map((categoria) => (
          <button
            key={categoria.id}
            className={filtroCategoria === chaveCategoria(categoria) ? 'filtro-ativo' : ''}
            aria-pressed={filtroCategoria === chaveCategoria(categoria)}
            onClick={() => carregarComFiltro(chaveCategoria(categoria))}
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
      {!carregandoCategorias && !erroCategorias && categoriasPublicas.length === 0 && (
        <p className="ranking-categories-state">Nenhuma categoria disponível para filtro.</p>
      )}

      {carregandoRanking && (
        <p className="ranking-categories-state" role="status">Carregando ranking global...</p>
      )}
      {!carregandoRanking && erroRanking && (
        <div className="ranking-categories-state ranking-categories-state--error" role="alert">
          <span>{erroRanking}</span>
          <button className="button-link" onClick={tentarRankingNovamente}>
            Tentar novamente
          </button>
        </div>
      )}
      {!carregandoRanking && !erroRanking && (ranking.length === 0 ? (
          <section className="ranking-empty">
            <span className="ranking-empty__signal" aria-hidden="true" />
            <h2>Ranking vazio</h2>
            <p>
              {filtroCategoria === null
                ? 'Ainda não existem resultados oficiais no ranking global.'
                : `Ainda não existem resultados em ${filtroAtual}.`}
            </p>
          </section>
        ) : (
          <ol className="ranking" aria-label={`Classificação: ${filtroAtual}`}>
            {ranking.map((resultado) => (
              <li className="ranking-item" key={`${resultado.posicao}:${resultado.categoria.id}:${resultado.jogador}`}>
                <span className="ranking-posicao" aria-label={`${resultado.posicao}ª posição`}>
                  {String(resultado.posicao).padStart(2, '0')}
                </span>
                <div className="ranking-jogador">
                  <strong>{resultado.jogador}</strong>
                  <small>{resultado.acertos} acertos · {resultado.categoria.nome}</small>
                </div>
                <strong className="ranking-pontos">
                  {new Intl.NumberFormat('pt-BR').format(resultado.pontuacao)} <small>pts</small>
                </strong>
              </li>
            ))}
          </ol>
        ))}

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
