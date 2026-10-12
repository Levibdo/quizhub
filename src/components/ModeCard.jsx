function ModeCard({
  eyebrow,
  title,
  description,
  metadata,
  actionLabel,
  onAction,
  disabled = false,
  indice,
}) {
  return (
    <article className={`mode-card mode-card--${indice}`}>
      <span className="mode-card__glyph" aria-hidden="true">
        {indice === 1 ? '◈' : '◉'}
      </span>
      <div className="mode-card__header">
        <span className="mode-card__eyebrow">{eyebrow}</span>
        <span className="mode-card__index" aria-hidden="true">{String(indice).padStart(2, '0')}</span>
      </div>

      <h2>{title}</h2>
      <p>{description}</p>

      <ul className="mode-card__metadata" aria-label="Regras do modo">
        {metadata.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <button
        className="mode-card__action"
        onClick={onAction}
        disabled={disabled}
      >
        {actionLabel}
      </button>
    </article>
  )
}

export default ModeCard
