import AnswerOption from './quiz/AnswerOption'
import QuestionCard from './quiz/QuestionCard'
import QuizHud from './quiz/QuizHud'

const LETRAS = ['A', 'B', 'C', 'D']

function TelaQuiz({
  pergunta,
  categoria,
  perguntaAtual,
  totalPerguntas,
  pontuacao,
  tempoRestante,
  tempoTotal,
  responder,
  respostaSelecionada,
  respondido,
  enviando,
  resultadoResposta,
  proximaPergunta,
  avancando,
}) {
  function estadoAlternativa(indice) {
    if (!respondido) {
      return enviando && indice === respostaSelecionada ? 'selecionada' : ''
    }

    if (indice === resultadoResposta?.alternativa_correta) {
      return 'correta'
    }

    if (indice === respostaSelecionada && resultadoResposta?.correta === false) {
      return 'errada'
    }

    return 'atenuada'
  }

  return (
    <section className="quiz-screen">
      <QuizHud
        categoria={categoria}
        perguntaAtual={perguntaAtual + 1}
        totalPerguntas={totalPerguntas}
        pontuacao={pontuacao}
        tempoRestante={tempoRestante}
        tempoTotal={tempoTotal}
      />

      <QuestionCard>{pergunta.pergunta}</QuestionCard>

      <div className="alternativas">
        {pergunta.alternativas.map((alternativa, indice) => (
          <AnswerOption
            key={indice}
            letra={LETRAS[indice]}
            alternativa={alternativa}
            indice={indice}
            estado={estadoAlternativa(indice)}
            disabled={respondido || enviando}
            onSelect={responder}
          />
        ))}
      </div>

      {enviando && !respondido && (
        <div className="feedback" role="status">Enviando resposta...</div>
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
    </section>
  )
}

export default TelaQuiz
