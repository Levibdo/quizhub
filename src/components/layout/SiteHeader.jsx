import { CosmicEye } from '../CosmicSigil'

function SiteHeader({ aoClicarMarca, usuario }) {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <a className="site-brand" href="/" aria-label="QuizHub — ir para a página inicial" onClick={aoClicarMarca}>
          <span className="site-brand__mark" aria-hidden="true">
            <svg className="cosmic-eye-logo" viewBox="40 65 160 112" focusable="false">
              <CosmicEye />
            </svg>
          </span>
          <span className="site-brand__name">QUIZHUB</span>
        </a>

        {usuario && (
          <div className="site-session" aria-label={`Sessão ativa: ${usuario.nome}`}>
            <span className="site-session__label">Sessão ativa</span>
            <strong title={usuario.nome}>{usuario.nome}</strong>
          </div>
        )}
      </div>
    </header>
  )
}

export default SiteHeader
