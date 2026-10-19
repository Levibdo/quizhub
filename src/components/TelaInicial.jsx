import CosmicSigil from './CosmicSigil'

function TelaInicial({
  usuario, bloqueado, convidado, entrar, continuarJogos,
}) {
  return (
    <section className="welcome-screen" aria-labelledby="welcome-title">
      <div className="welcome-sigil" aria-hidden="true">
          <CosmicSigil />
          <span>QH</span>
      </div>

      <div className="welcome-copy">
        <span className="home-eyebrow">Conhecimento, estratégia e diversão</span>
        <h1 id="welcome-title">Bem-vindo ao QuizHub!</h1>
        <p>Teste seus conhecimentos, desafie seus amigos e descubra até onde você consegue chegar!</p>
      </div>

      <div className="welcome-actions" aria-label="Como deseja começar?">
        {usuario ? (
          <button className="welcome-actions__primary" disabled={bloqueado} onClick={continuarJogos}>Continuar para os jogos</button>
        ) : (
          <>
            <button className="welcome-actions__primary" disabled={bloqueado} onClick={convidado}>Jogar como convidado</button>
            <button className="button-secondary" disabled={bloqueado} onClick={entrar}>Fazer login</button>
          </>
        )}
      </div>
      <p className="welcome-note">Dois modos. Uma pergunta inevitável: até onde você chega?</p>
    </section>
  )
}

export default TelaInicial
