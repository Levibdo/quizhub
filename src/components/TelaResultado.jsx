import { categorias } from '../data/categorias'

function TelaResultado({
  jogador,
  acertos,
  erros,
  pontuacao,
  categoriaSelecionada,
  iniciarQuiz,
  verRanking,
}) {
  const categoria = categorias.find(
    (item) => item.id === categoriaSelecionada
  )

  return (
    <>
      <h1>Resultado</h1>
        <p>
        Jogador: <strong>{jogador}</strong>
        </p>
      {categoria && (
        <p>
          Categoria: <strong>{categoria.nome}</strong>
        </p>
      )}

      <p>Acertos: {acertos}</p>
      <p>Erros: {erros}</p>
      <p>Pontuação: {pontuacao}</p>
      <button onClick={verRanking}>
       Ver ranking
     </button>

      <button onClick={iniciarQuiz}>
        Jogar novamente
      </button>
    </>
  )
}

export default TelaResultado