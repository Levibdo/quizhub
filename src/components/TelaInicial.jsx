import ModeCard from './ModeCard'

function TelaInicial({
  usuario, bloqueado, jogar, convidado, entrar, cadastrar, sair,
  verRanking,
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
      </div>

      <nav className="home-actions" aria-label="Ações da página inicial">
        {usuario ? (
          <>
            <button className="button-secondary" disabled={bloqueado} onClick={sair}>Sair</button>
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
