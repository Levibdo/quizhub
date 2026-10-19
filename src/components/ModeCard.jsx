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
      <button
        className="mode-card__hit-area"
        type="button"
        onClick={onAction}
        disabled={disabled}
        aria-label={actionLabel}
      >
        <span className="mode-card__hit-label">{actionLabel}</span>
      </button>

      <span className="mode-card__glyph" aria-hidden="true">
        {indice === 1 ? '◈' : '◉'}
      </span>
      <div className="mode-card__header">
        <span className="mode-card__eyebrow">{eyebrow}</span>
        <span className="mode-card__index" aria-hidden="true">{String(indice).padStart(2, '0')}</span>
      </div>

      <div className="mode-card__body">
        <h2>{title}</h2>
        <p>{description}</p>

        <ul className="mode-card__metadata" aria-label="Características do modo">
          {metadata.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <span className="mode-card__action" aria-hidden="true">
        {actionLabel}
      </span>
    </article>
  )
}

export default ModeCard
