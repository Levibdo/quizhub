function TelaResultado({
  acertos,
  erros,
  pontuacao,
  iniciarQuiz,
}) {
  return (
    <>
      <h1>Resultado</h1>

      <p>Acertos: {acertos}</p>
      <p>Erros: {erros}</p>
      <p>Pontuação: {pontuacao}</p>

      <button onClick={iniciarQuiz}>
        Jogar novamente
      </button>
    </>
  )
}

export default TelaResultado