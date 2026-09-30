import { formatarAproveitamento } from '../utils/aproveitamento'

function TelaResultado({
    jogador,
    acertos,
    erros,
    pontuacao,
    categoria,
    iniciarQuiz,
    verRanking,
    voltarInicio,
}) {
    const aproveitamento = formatarAproveitamento(acertos, erros)

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
            <p>Aproveitamento: {aproveitamento}</p>
            <p>Pontuação: {pontuacao}</p>
            <button onClick={verRanking}>
                Ver ranking
            </button>

            <button onClick={iniciarQuiz}>
                Jogar novamente
            </button>
            <button onClick={voltarInicio}>
                Início
            </button>

        </>
    )
}

export default TelaResultado
