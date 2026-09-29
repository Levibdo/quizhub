import { categorias } from '../data/categorias'

function TelaCategorias({ selecionarCategoria, carregando }) {
  return (
    <>
      <h1>Escolha uma categoria</h1>

      <p>
        Selecione o tema das perguntas que deseja responder.
      </p>

      <div className="categorias">
        {categorias.map((categoria) => (
          <button
            key={categoria.id}
            className="categoria-card"
            onClick={() => selecionarCategoria(categoria.id)}
            disabled={carregando}
          >
            <span className="categoria-icone">
              {categoria.icone}
            </span>

            <span className="categoria-info">
              <strong>{categoria.nome}</strong>
              <small>{categoria.descricao}</small>
            </span>
          </button>
        ))}
      </div>
      {carregando && <p>Iniciando partida...</p>}
    </>
  )
}

export default TelaCategorias
