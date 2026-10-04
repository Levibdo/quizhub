function SiteHeader({ aoClicarMarca }) {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <a className="site-brand" href="/" aria-label="QuizHub — ir para a página inicial" onClick={aoClicarMarca}>
          <span className="site-brand__mark" aria-hidden="true">QH</span>
          <span className="site-brand__name">QUIZHUB</span>
        </a>

        <div className="site-header__controls" aria-hidden="true" />
      </div>
    </header>
  )
}

export default SiteHeader
