function NemAPatoEntry({
  carregando,
  codigo,
  erro,
  formulario,
  nome,
  sucesso,
  aoAlterarCodigo,
  aoAlterarNome,
  aoEscolherFormulario,
  aoEnviar,
  aoVoltar,
}) {
  return (
    <section className="np-screen np-screen--entry" aria-labelledby="np-title" aria-busy={carregando}>
      <div className="np-entry-scene" aria-hidden="true" />
      <header className="np-heading">
        <span className="np-eyebrow">QuizHub // Modo multiplayer</span>
        <h1 id="np-title">NEM A PATO!</h1>
        <p>3–6 jogadores · 10 rodadas · 2 minutos por rodada</p>
        <p className="np-heading__rule">Quem terminar com menos patos vence.</p>
      </header>
      {erro && <p className="np-message np-message--error" role="alert">{erro}</p>}
      {sucesso && <p className="np-message" role="status">{sucesso}</p>}
      {!formulario ? (
        <div className="np-actions">
          <button type="button" onClick={() => aoEscolherFormulario('criar')}>Criar sala</button>
          <button type="button" className="button-secondary" onClick={() => aoEscolherFormulario('entrar')}>Entrar em sala</button>
          <button type="button" className="button-ghost" onClick={aoVoltar}>Voltar ao QuizHub</button>
        </div>
      ) : (
        <form className="np-form" onSubmit={(event) => { event.preventDefault(); aoEnviar(formulario) }}>
          {formulario === 'entrar' && (
            <label htmlFor="np-code">
              Código da sala
              <input
                id="np-code"
                name="codigo"
                value={codigo}
                onChange={(event) => aoAlterarCodigo(event.target.value)}
                autoCapitalize="characters"
                autoComplete="off"
                autoCorrect="off"
                inputMode="text"
                spellCheck={false}
                maxLength={6}
                required
              />
            </label>
          )}
          <label htmlFor="np-name">
            Seu nome
            <input
              id="np-name"
              name="nome"
              value={nome}
              onChange={(event) => aoAlterarNome(event.target.value)}
              autoComplete="nickname"
              maxLength={100}
              required
            />
          </label>
          <button type="submit" disabled={carregando}>
            {carregando ? (formulario === 'criar' ? 'Criando sala...' : 'Entrando...') : formulario === 'criar' ? 'Criar sala' : 'Entrar'}
          </button>
          <button type="button" className="button-ghost" disabled={carregando} onClick={() => aoEscolherFormulario(null)}>Voltar</button>
        </form>
      )}
    </section>
  )
}

export default NemAPatoEntry
