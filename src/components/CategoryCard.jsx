const SIMBOLOS = {
  geral: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M4 12h16M12 4c2.3 2.2 3.5 4.9 3.5 8S14.3 17.8 12 20c-2.3-2.2-3.5-4.9-3.5-8S9.7 6.2 12 4Z" />
    </>
  ),
  matematica: (
    <>
      <path d="M5 5h14M5 19h14M8 9l8 6M16 9l-8 6" />
      <circle cx="12" cy="12" r="9" />
    </>
  ),
  tecnologia: (
    <>
      <rect x="6" y="6" width="12" height="12" rx="1" />
      <path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4M10 10h4v4h-4Z" />
    </>
  ),
  entretenimento: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m10 8 6 4-6 4V8Z" />
    </>
  ),
}

function iniciais(nome) {
  const partes = nome.trim().split(/\s+/).filter(Boolean)
  return partes.slice(0, 2).map((parte) => parte[0]).join('').toUpperCase() || 'QH'
}

function CategorySymbol({ categoria }) {
  const simbolo = SIMBOLOS[categoria.id]
  if (!simbolo) {
    return (
      <span
        className="category-symbol category-symbol--fallback"
        data-symbol="fallback"
        aria-hidden="true"
      >
        {iniciais(categoria.nome)}
      </span>
    )
  }

  return (
    <span className="category-symbol" data-symbol={categoria.id} aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false">
        {simbolo}
      </svg>
    </span>
  )
}

function CategoryCard({ categoria, indice, onSelect, disabled }) {
  return (
    <button
      className="categoria-card"
      onClick={() => onSelect(categoria.id)}
      disabled={disabled}
      aria-busy={disabled || undefined}
    >
      <span className="categoria-card__topline">
        <span className="categoria-card__index">
          {String(indice + 1).padStart(2, '0')}
        </span>
        <CategorySymbol categoria={categoria} />
      </span>

      <span className="categoria-info">
        <strong>{categoria.nome}</strong>
        <small>{categoria.descricao || 'Desafio de conhecimentos.'}</small>
      </span>

      <span className="categoria-card__footer">
        <span>Quiz Clássico</span>
        <span className="categoria-card__action">
          {disabled ? 'Iniciando...' : 'Iniciar teste'}
        </span>
      </span>
    </button>
  )
}

export default CategoryCard
