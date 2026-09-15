function TelaInicial({ iniciarQuiz }) {
  return (
    <>
      <h1>Quiz</h1>
      <p>Teste seus conhecimentos!</p>

      <button onClick={iniciarQuiz}>
        Iniciar Quiz
      </button>
    </>
  )
}

export default TelaInicial