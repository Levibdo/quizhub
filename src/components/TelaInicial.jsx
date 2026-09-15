function TelaInicial({ escolherCategoria }) {
  return (
    <>
      <h1>Quiz</h1>
      <p>Teste seus conhecimentos!</p>

      <button onClick={escolherCategoria}>
        Iniciar Quiz
      </button>
    </>
  )
}

export default TelaInicial