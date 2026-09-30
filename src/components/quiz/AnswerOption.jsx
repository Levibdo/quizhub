function AnswerOption({
  letra,
  alternativa,
  indice,
  estado,
  disabled,
  onSelect,
}) {
  const rotulos = {
    correta: 'Correta',
    errada: 'Incorreta',
    selecionada: 'Enviando',
  }
  const rotulo = rotulos[estado]

  return (
    <button
      className={estado}
      onClick={() => onSelect(indice)}
      disabled={disabled}
      aria-label={`${letra}: ${alternativa}${rotulo ? `. ${rotulo}.` : ''}`}
    >
      <span className="letra-alternativa" aria-hidden="true">{letra}</span>
      <span className="answer-option__text">{alternativa}</span>
      {rotulo && <span className="answer-option__status">{rotulo}</span>}
    </button>
  )
}

export default AnswerOption
