import CategoryCard from './CategoryCard'

function TelaCategorias({
  categorias,
  selecionarCategoria,
  carregando,
  carregandoCategorias,
  erroCategorias,
  tentarNovamente,
}) {
  const disponivel = !carregandoCategorias && !erroCategorias

  return (
    <section className="categories-screen" aria-labelledby="categories-title">
      <header className="categories-header">
        <span className="categories-header__eyebrow">
          QuizHub // Seleção de desafio
        </span>
        <h1 id="categories-title">Escolha o teste</h1>
        <p>Selecione uma categoria e coloque seu conhecimento à prova.</p>
      </header>

      {carregandoCategorias && (
        <div className="categories-state" role="status">
          <span className="categories-state__signal" aria-hidden="true" />
          <strong>Carregando categorias...</strong>
          <p>Consultando os desafios disponíveis.</p>
        </div>
      )}

      {erroCategorias && (
        <div className="categories-state categories-state--error" role="alert">
          <strong>Não foi possível acessar os desafios.</strong>
          <p>{erroCategorias}</p>
          <button onClick={tentarNovamente}>Tentar novamente</button>
        </div>
      )}

      {disponivel && categorias.length === 0 && (
        <div className="categories-state">
          <strong>Nenhuma categoria disponível.</strong>
          <p>Não há desafios liberados para iniciar uma partida agora.</p>
        </div>
      )}

      {disponivel && categorias.length > 0 && (
        <div className="categorias">
          {categorias.map((categoria, indice) => (
            <CategoryCard
              key={categoria.id}
              categoria={categoria}
              indice={indice}
              onSelect={selecionarCategoria}
              disabled={carregando || carregandoCategorias}
            />
          ))}
        </div>
      )}

      {carregando && (
        <p className="categories-starting" role="status">
          Iniciando partida...
        </p>
      )}
    </section>
  )
}

export default TelaCategorias
