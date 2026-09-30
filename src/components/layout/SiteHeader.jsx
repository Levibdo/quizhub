function SiteHeader() {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <div className="site-brand" aria-label="QuizHub">
          <span className="site-brand__mark" aria-hidden="true">QH</span>
          <span className="site-brand__name">QUIZHUB</span>
        </div>

        <div className="site-header__controls" aria-hidden="true" />
      </div>
    </header>
  )
}

export default SiteHeader
