function ModeCard({
  eyebrow,
  title,
  description,
  metadata,
  actionLabel,
  onAction,
  disabled = false,
}) {
  return (
    <article className="mode-card">
      <div className="mode-card__header">
        <span className="mode-card__eyebrow">{eyebrow}</span>
        <span className="mode-card__index" aria-hidden="true">01</span>
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
