import { useState } from 'react'
import AuthPanel from './AuthPanel'

function TelaJogador({ confirmarJogador, voltar }) {
  const [nome, setNome] = useState('')
  const [erro, setErro] = useState('')

  function enviarFormulario(evento) {
    evento.preventDefault()

    const nomeLimpo = nome.trim()

    if (!nomeLimpo) {
      setErro('Informe um nome ou apelido para continuar.')
      return
    }

    setErro('')
    confirmarJogador(nomeLimpo)
  }

  return (
    <AuthPanel
      eyebrow="Identificação"
      title="Quem vai jogar?"
      description="Digite seu nome ou apelido para continuar."
      footer={<button className="button-ghost auth-panel__back" onClick={voltar}>Voltar</button>}
    >
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      <form className="auth-form" onSubmit={enviarFormulario}>
        <label htmlFor="jogador-nome">Nome ou apelido</label>
        <input
          id="jogador-nome"
          type="text"
          value={nome}
          onChange={(evento) =>
            setNome(evento.target.value)
          }
          placeholder="Nome ou apelido"
          maxLength={20}
          required
          autoFocus
        />

        <button className="auth-form__submit" type="submit">Continuar</button>
      </form>
    </AuthPanel>
  )
}

export default TelaJogador
