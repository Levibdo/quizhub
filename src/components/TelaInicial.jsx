function TelaInicial({
  usuario, bloqueado, jogar, convidado, entrar, cadastrar, sair,
  verRanking,
}) {
  return (
    <>
      <h1>QuizHub</h1>

      <p>
        Teste seus conhecimentos e conquiste a maior
        pontuação.
      </p>

      {usuario ? (
        <>
          <p>Olá, {usuario.nome}</p>
          <button disabled={bloqueado} onClick={jogar}>Jogar</button>
          <button disabled={bloqueado} onClick={sair}>Sair</button>
          <button disabled={bloqueado} onClick={convidado}>Sair e jogar como convidado</button>
        </>
      ) : (
        <>
          <button disabled={bloqueado} onClick={convidado}>Jogar como convidado</button>
          <button disabled={bloqueado} onClick={entrar}>Entrar</button>
          <button disabled={bloqueado} onClick={cadastrar}>Criar conta</button>
        </>
      )}

      <button disabled={bloqueado} onClick={verRanking}>
        Ver ranking
      </button>
    </>
  )
}

export default TelaInicial
