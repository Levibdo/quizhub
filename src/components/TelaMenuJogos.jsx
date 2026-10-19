import CosmicSigil from './CosmicSigil'
import ModeCard from './ModeCard'

function TelaMenuJogos({ bloqueado, jogar, nemAPato, verRanking }) {
  return (
    <section className="game-menu-screen" aria-labelledby="game-menu-title">
      <header className="game-menu-hero">
        <div className="game-menu-sigil" aria-hidden="true">
          <CosmicSigil compacto />
        </div>
        <div className="game-menu-copy">
          <span className="home-eyebrow">Escolha seu desafio</span>
          <h1 id="game-menu-title">Você sabe a resposta?</h1>
          <p>Prove antes que o tempo acabe.</p>
        </div>
      </header>

      <div className="home-modes">
        <ModeCard
          indice={1}
          eyebrow="Modo individual"
          title="Quiz Clássico"
          description="Conhecimento, precisão e velocidade em uma sequência de dez desafios."
          metadata={[
            '10 perguntas',
            '15 segundos por pergunta',
            'Pontuação influenciada pelo tempo',
          ]}
          actionLabel="Jogar"
          onAction={jogar}
          disabled={bloqueado}
        />
        <ModeCard
          indice={2}
          eyebrow="Modo multiplayer"
          title="Nem a Pato!"
          description="Crie uma sala ou entre com o código para reunir seus amigos."
          metadata={['3 a 6 jogadores', 'Notebook ou celular', 'Partida em tempo real']}
          actionLabel="Abrir Nem a Pato"
          onAction={nemAPato}
          disabled={bloqueado}
        />
      </div>

      <div className="home-discover">
        <span>Compare seu melhor resultado com outros jogadores.</span>
        <button className="button-secondary" disabled={bloqueado} onClick={verRanking}>Ver ranking</button>
      </div>
    </section>
  )
}

export default TelaMenuJogos
