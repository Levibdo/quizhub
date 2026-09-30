const ICONES_CONHECIDOS = {
  geral: '🌎',
  tecnologia: '💻',
  matematica: '🧮',
}

function TelaCategorias({
  categorias,
  selecionarCategoria,
  carregando,
  carregandoCategorias,
  erroCategorias,
  tentarNovamente,
}) {
  return (
    <>
      <h1>Escolha uma categoria</h1>

      <p>
        Selecione o tema das perguntas que deseja responder.
      </p>

      {carregandoCategorias && <p role="status">Carregando categorias...</p>}

      {erroCategorias && (
        <div role="alert">
          <p>{erroCategorias}</p>
          <button onClick={tentarNovamente}>Tentar novamente</button>
        </div>
      )}

      {!carregandoCategorias && !erroCategorias && (
        <div className="categorias">
          {categorias.map((categoria) => (
            <button
              key={categoria.id}
              className="categoria-card"
              onClick={() => selecionarCategoria(categoria.id)}
              disabled={carregando || carregandoCategorias}
            >
              <span className="categoria-icone">
                {ICONES_CONHECIDOS[categoria.id] ?? '❓'}
              </span>

              <span className="categoria-info">
                <strong>{categoria.nome}</strong>
                <small>{categoria.descricao}</small>
              </span>
            </button>
          ))}
        </div>
      )}
      {carregando && <p>Iniciando partida...</p>}
    </>
  )
}

export default TelaCategorias
