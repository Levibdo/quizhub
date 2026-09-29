function TelaInicial({
  escolherCategoria,
  verRanking,
}) {
  return (
    <>
      <h1>QuizHub</h1>

      <p>
        Teste seus conhecimentos e conquiste a maior
        pontuação.
      </p>

      <button onClick={escolherCategoria}>
        Jogar
      </button>

      <button onClick={verRanking}>
        Ver ranking
      </button>
    </>
  )
}

export default TelaInicial