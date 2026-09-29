import { useState } from 'react'

export default function TelaLogin({ entrar, criarConta, voltar, carregando, erro }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  return (
    <>
      <h1>Entrar</h1>
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      <form className="form-jogador" onSubmit={(evento) => {
        evento.preventDefault()
        if (!carregando) entrar(email.trim(), senha)
      }}>
        <label htmlFor="login-email">E-mail</label>
        <input id="login-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} disabled={carregando} />
        <label htmlFor="login-senha">Senha</label>
        <input id="login-senha" type="password" autoComplete="current-password" required maxLength={128} value={senha} onChange={(e) => setSenha(e.target.value)} disabled={carregando} />
        <button disabled={carregando}>{carregando ? 'Entrando...' : 'Entrar'}</button>
      </form>
      <button disabled={carregando} onClick={criarConta}>Criar conta</button>
      <button disabled={carregando} onClick={voltar}>Voltar</button>
    </>
  )
}
