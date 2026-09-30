function TelaQuiz({
  pergunta,
  perguntaAtual,
  totalPerguntas,
  pontuacao,
  tempoRestante,
  responder,
  respostaSelecionada,
  respondido,
  enviando,
  resultadoResposta,
  proximaPergunta,
  avancando,
}) {
  const progresso =
    ((perguntaAtual + 1) / totalPerguntas) * 100

  const letras = ['A', 'B', 'C', 'D']

  function classeAlternativa(indice) {
    if (!respondido) {
      return ''
    }

    if (indice === resultadoResposta?.alternativa_correta) {
      return 'correta'
    }

    if (indice === respostaSelecionada && resultadoResposta?.correta === false) {
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
            disabled={respondido || enviando}
          >
            <span className="letra-alternativa">
              {letras[indice]}
            </span>

            <span>{alternativa}</span>
          </button>
        ))}
      </div>

      {enviando && !respondido && (
        <div className="feedback">Enviando resposta...</div>
      )}

      {respondido && resultadoResposta && (
        <section className="feedback" aria-live="polite">
          <strong>
            {resultadoResposta.timeout ? 'Tempo esgotado.'
              : resultadoResposta.correta ? 'Resposta correta!' : 'Resposta incorreta.'}
          </strong>
          <p>Resposta correta: {pergunta.alternativas[resultadoResposta.alternativa_correta]}</p>
          <div className="explicacao">
            <strong>Explicação:</strong>
            <p>{resultadoResposta.explicacao}</p>
          </div>
          <span>+{resultadoResposta.pontos_ganhos} pontos</span>
          <button className="proxima-pergunta" onClick={proximaPergunta} disabled={avancando}>
            {avancando ? 'Aguarde...'
              : resultadoResposta.status === 'FINALIZADA' ? 'Ver resultado' : 'Próxima pergunta'}
          </button>
        </section>
      )}
    </>
  )
}

export default TelaQuiz
