import { useEffect, useState } from 'react'
import { listarRankingPessoal } from '../../services/api'

export default function PainelRankingPessoal({ modo, aoExpirarSessao }) {
  const [categorias, setCategorias] = useState([])
  const [carregando, setCarregando] = useState(modo === 'QUIZ_CLASSICO')
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)

  useEffect(() => {
    if (modo !== 'QUIZ_CLASSICO') {
      return undefined
    }
    let ativa = true
    listarRankingPessoal()
      .then((resultado) => { if (ativa) setCategorias(resultado) })
      .catch((error) => {
        if (!ativa) return
        if (error.status === 401) aoExpirarSessao()
        else setErro(`Não foi possível carregar seu ranking. ${error.message}`)
      })
      .finally(() => { if (ativa) setCarregando(false) })
    return () => { ativa = false }
  }, [aoExpirarSessao, modo, tentativa])

  if (modo !== 'QUIZ_CLASSICO') {
    return (
      <section className="personal-ranking" aria-labelledby="personal-ranking-title">
        <div className="content-section-heading">
          <div><span className="content-eyebrow">Ranking individual</span><h2 id="personal-ranking-title">Melhores partidas</h2></div>
        </div>
        <div className="content-empty"><strong>Disponível no Quiz Clássico.</strong><p>O Nem a Pato mantém seu fluxo próprio e não participa deste ranking.</p></div>
      </section>
    )
  }

  return (
    <section className="personal-ranking" aria-labelledby="personal-ranking-title" aria-busy={carregando}>
      <div className="content-section-heading">
        <div><span className="content-eyebrow">Ranking individual</span><h2 id="personal-ranking-title">Melhores partidas</h2></div>
      </div>
      <p className="personal-ranking__intro">Suas partidas concluídas, organizadas pela pontuação oficial em cada categoria própria.</p>
      {carregando && <div className="content-state" role="status">Carregando seu ranking...</div>}
      {erro && <div className="content-state content-state--error" role="alert"><p>{erro}</p><button type="button" onClick={() => { setErro(''); setCarregando(true); setTentativa((valor) => valor + 1) }}>Tentar novamente</button></div>}
      {!carregando && !erro && categorias.length === 0 && (
        <div className="content-empty"><strong>Nenhuma categoria própria.</strong><p>Crie uma categoria do Quiz Clássico para começar.</p></div>
      )}
      {!carregando && !erro && categorias.length > 0 && (
        <div className="personal-ranking__categories">
          {categorias.map((categoria) => (
            <section key={categoria.categoria_id} className="personal-ranking__category" aria-labelledby={`personal-ranking-${categoria.categoria_id}`}>
              <h3 id={`personal-ranking-${categoria.categoria_id}`}>{categoria.categoria_nome}</h3>
              {categoria.partidas.length === 0 ? (
                <p className="personal-ranking__empty">Nenhuma partida concluída nesta categoria.</p>
              ) : (
                <ol className="personal-ranking__list">
                  {categoria.partidas.map((partida) => (
                    <li key={partida.partida_id} className="personal-ranking__item">
                      <strong className="personal-ranking__position">{partida.posicao}º</strong>
                      <span className="personal-ranking__game">
                        <small>Partida</small>
                        <code title={partida.partida_id} aria-label={`Identificador completo da partida: ${partida.partida_id}`}>
                          #{partida.partida_id.slice(0, 8)}
                        </code>
                      </span>
                      <span className="personal-ranking__score"><strong>{partida.pontuacao}</strong><small>pontos</small></span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          ))}
        </div>
      )}
    </section>
  )
}
