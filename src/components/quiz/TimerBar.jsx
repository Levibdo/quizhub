function TimerBar({ tempoRestante, tempoTotal, urgente }) {
  const percentual = Math.max(0, Math.min(100, (tempoRestante / tempoTotal) * 100))

  return (
    <div
      className={`timer-bar ${urgente ? 'timer-bar--urgente' : ''}`}
      role="progressbar"
      aria-label="Tempo restante"
      aria-valuemin="0"
      aria-valuemax={tempoTotal}
      aria-valuenow={tempoRestante}
    >
      <span className="timer-bar__fill" style={{ width: `${percentual}%` }} />
    </div>
  )
}

export default TimerBar
