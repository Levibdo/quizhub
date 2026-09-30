import { useState } from 'react'
import AuthPanel from './AuthPanel'

export default function TelaLogin({ entrar, criarConta, voltar, carregando, erro }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  return (
    <AuthPanel
      eyebrow="Acesso"
      title="Entrar no QuizHub"
      description="Retome sua sessão e encare o próximo desafio."
      footer={(
        <>
          <p>Não tem uma conta?</p>
          <button className="button-link" disabled={carregando} onClick={criarConta}>Criar conta</button>
          <button className="button-ghost auth-panel__back" disabled={carregando} onClick={voltar}>Voltar</button>
        </>
      )}
    >
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      <form className="auth-form" onSubmit={(evento) => {
        evento.preventDefault()
        if (!carregando) entrar(email.trim(), senha)
      }}>
        <label htmlFor="login-email">E-mail</label>
        <input id="login-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} disabled={carregando} />
        <label htmlFor="login-senha">Senha</label>
        <input id="login-senha" type="password" autoComplete="current-password" required maxLength={128} value={senha} onChange={(e) => setSenha(e.target.value)} disabled={carregando} />
        <button className="auth-form__submit" disabled={carregando}>{carregando ? 'Entrando...' : 'Entrar'}</button>
      </form>
    </AuthPanel>
  )
}
