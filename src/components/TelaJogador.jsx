import { useState } from 'react'

function TelaJogador({ confirmarJogador }) {
  const [nome, setNome] = useState('')

  function enviarFormulario(evento) {
    evento.preventDefault()

    const nomeLimpo = nome.trim()

    if (!nomeLimpo) {
      return
    }

    confirmarJogador(nomeLimpo)
  }

  return (
    <>
      <h1>Quem vai jogar?</h1>

      <p>
        Digite seu nome ou apelido para continuar.
      </p>

      <form
        className="form-jogador"
        onSubmit={enviarFormulario}
      >
        <input
          type="text"
          value={nome}
          onChange={(evento) =>
            setNome(evento.target.value)
          }
          placeholder="Nome ou apelido"
          maxLength={20}
          autoFocus
        />

        <button type="submit">
          Continuar
        </button>
      </form>
    </>
  )
}

export default TelaJogador