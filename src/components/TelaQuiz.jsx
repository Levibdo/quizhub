function TelaQuiz({
  pergunta,
  perguntaAtual,
  totalPerguntas,
  pontuacao,
  tempoRestante,
  responder,
  respostaSelecionada,
  respondido,
  pontosUltimaResposta,
}) {
  const progresso =
    ((perguntaAtual + 1) / totalPerguntas) * 100

  const letras = ['A', 'B', 'C', 'D']

  function classeAlternativa(indice) {
    if (!respondido) {
      return ''
    }

    if (indice === pergunta.correta) {
      return 'correta'
    }

    if (indice === respostaSelecionada) {
      return 'errada'
    }

    return ''
  }

  return (
    <>
      <div className="info-quiz">
        <span>
          Pergunta {perguntaAtual + 1} de {totalPerguntas}
        </span>

        <span>
          Pontuação: {pontuacao}
        </span>

        <span
          className={`timer ${
            tempoRestante <= 5 ? 'timer-urgente' : ''
          }`}
        >
          ⏱ {tempoRestante}s
        </span>
      </div>

      <div className="progresso">
        <div
          className="progresso-barra"
          style={{ width: `${progresso}%` }}
        />
      </div>

      <h2>{pergunta.pergunta}</h2>

      <div className="alternativas">
        {pergunta.alternativas.map((alternativa, indice) => (
          <button
            key={indice}
            className={classeAlternativa(indice)}
            onClick={() => responder(indice)}
            disabled={respondido}
          >
            <span className="letra-alternativa">
              {letras[indice]}
            </span>

            <span>{alternativa}</span>
          </button>
        ))}
      </div>

      {respondido && (
        <div className="feedback">
          {respostaSelecionada === null ? (
            <strong>⏱ Tempo esgotado!</strong>
          ) : respostaSelecionada === pergunta.correta ? (
            <>
              <strong>✓ Resposta correta!</strong>
              <span>
                +{pontosUltimaResposta} pontos
              </span>
            </>
          ) : (
            <strong>✕ Resposta incorreta</strong>
          )}
        </div>
      )}
    </>
  )
}

export default TelaQuiz