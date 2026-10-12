import CosmicSigil from './CosmicSigil'

function AuthPanel({ eyebrow, title, description, children, footer }) {
  return (
    <section className="auth-screen" aria-labelledby="auth-panel-title">
      <div className="auth-screen__sigil" aria-hidden="true">
        <CosmicSigil compacto />
      </div>
      <div className="auth-panel">
        <span className="auth-panel__corner auth-panel__corner--top" aria-hidden="true" />
        <span className="auth-panel__corner auth-panel__corner--bottom" aria-hidden="true" />
        <header className="auth-panel__header">
          <span className="auth-panel__eyebrow">{eyebrow}</span>
          <h1 id="auth-panel-title">{title}</h1>
          {description && <p>{description}</p>}
        </header>

        {children}

        {footer && <footer className="auth-panel__footer">{footer}</footer>}
      </div>
    </section>
  )
}

export default AuthPanel
