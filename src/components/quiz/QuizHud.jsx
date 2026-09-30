import TimerBar from './TimerBar'

function QuizHud({
  categoria,
  perguntaAtual,
  totalPerguntas,
  pontuacao,
  tempoRestante,
  tempoTotal,
}) {
  const urgente = tempoRestante <= 5
  const progresso = (perguntaAtual / totalPerguntas) * 100

  return (
    <header className={`quiz-hud ${urgente ? 'quiz-hud--urgente' : ''}`}>
      <p className="quiz-hud__context">
        QuizHub // {categoria?.nome || categoria?.id || 'Quiz Clássico'}
      </p>

      <div className="info-quiz">
        <span className="quiz-hud__stat">
          <small>Questão</small>
          <strong>{String(perguntaAtual).padStart(2, '0')} / {String(totalPerguntas).padStart(2, '0')}</strong>
        </span>

        <span className="quiz-hud__stat">
          <small>Pontuação</small>
          <strong>{String(pontuacao).padStart(4, '0')}</strong>
        </span>

        <span className="quiz-hud__stat quiz-hud__time">
          <small>Tempo</small>
          <span className={`timer ${urgente ? 'timer-urgente' : ''}`}>
            {tempoRestante}s
          </span>
        </span>
      </div>

      <TimerBar
        tempoRestante={tempoRestante}
        tempoTotal={tempoTotal}
        urgente={urgente}
      />

      <div
        className="quiz-progress"
        role="progressbar"
        aria-label="Progresso da partida"
        aria-valuemin="0"
        aria-valuemax={totalPerguntas}
        aria-valuenow={perguntaAtual}
      >
        <span style={{ width: `${progresso}%` }} />
      </div>
    </header>
  )
}

export default QuizHud
