import ModeCard from './ModeCard'

function TelaInicial({
  usuario, bloqueado, jogar, convidado, entrar, cadastrar, sair,
  verRanking, nemAPato, meuConteudo,
}) {
  return (
    <section className="home-screen" aria-labelledby="home-title">
      <div className="home-hero">
        <div className="home-sigil" aria-hidden="true">
          <span>QH</span>
        </div>

        <div className="home-copy">
          <span className="home-eyebrow">QuizHub // Desafio clássico</span>
          <h1 id="home-title">Você sabe a resposta?</h1>
          <p>Prove antes que o tempo acabe.</p>
        </div>
      </div>

      {usuario && (
        <div className="session-chip">
          <span>Sessão ativa</span>
          <strong>{usuario.nome}</strong>
        </div>
      )}

      <div className="home-modes">
        <ModeCard
          eyebrow="Modo disponível"
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
          eyebrow="Lobby multiplayer"
          title="Nem a Pato!"
          description="Crie uma sala ou entre com o código para reunir seus amigos."
          metadata={['3 a 6 jogadores', 'Entre pelo notebook ou celular', 'Aguardando modo de partida']}
          actionLabel="Abrir Nem a Pato"
          onAction={nemAPato}
          disabled={bloqueado}
        />
      </div>

      <nav className="home-actions" aria-label="Ações da página inicial">
        {usuario ? (
          <>
            <button className="button-secondary" disabled={bloqueado} onClick={sair}>Sair</button>
            <button className="button-secondary" disabled={bloqueado} onClick={meuConteudo}>Meu Conteúdo</button>
            <button className="button-ghost" disabled={bloqueado} onClick={convidado}>Sair e jogar como convidado</button>
          </>
        ) : (
          <>
            <button className="button-secondary" disabled={bloqueado} onClick={entrar}>Entrar</button>
            <button className="button-secondary" disabled={bloqueado} onClick={cadastrar}>Criar conta</button>
          </>
        )}
        <button className="button-ghost" disabled={bloqueado} onClick={verRanking}>Ver ranking</button>
      </nav>

      <p className="system-status">
        <span aria-hidden="true" /> QuizHub // Sistema online
      </p>
    </section>
  )
}

export default TelaInicial
