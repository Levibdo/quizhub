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
        <main className="result-screen">
            <header className="result-header">
                <p className="result-header__eyebrow">QuizHub // Teste concluído</p>
                <h1>Teste concluído</h1>
                <p>Você chegou ao fim do desafio. O resultado foi registrado.</p>
            </header>

            <section className="result-summary" aria-label="Resumo do resultado">
                <div className="result-score">
                    <span className="result-score__detail" aria-hidden="true" />
                    <strong>{aproveitamento}</strong>
                    <span>Aproveitamento</span>
                </div>

                <div className="result-stats">
                    <div className="result-stat result-stat--correct">
                        <span>Acertos</span>
                        <strong>{acertos}</strong>
                    </div>
                    <div className="result-stat result-stat--wrong">
                        <span>Erros</span>
                        <strong>{erros}</strong>
                    </div>
                    <div className="result-stat result-stat--points">
                        <span>Pontos</span>
                        <strong>{pontuacao}</strong>
                    </div>
                </div>
            </section>

            <dl className="result-identity">
                <div>
                    <dt>Jogador</dt>
                    <dd>{jogador}</dd>
                </div>
                {categoria && (
                    <div>
                        <dt>Categoria</dt>
                        <dd>{categoria.nome}</dd>
                    </div>
                )}
            </dl>

            <div className="result-actions">
                <button className="result-actions__primary" onClick={iniciarQuiz}>
                    Jogar novamente →
                </button>
                <div className="result-actions__secondary">
                    <button className="button-secondary" onClick={verRanking}>
                        Ver ranking
                    </button>
                    <button className="button-ghost" onClick={voltarInicio}>
                        Voltar ao início
                    </button>
                </div>
            </div>
        </main>
    )
}

export default TelaResultado
