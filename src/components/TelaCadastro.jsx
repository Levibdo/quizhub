import { useState } from 'react'
import AuthPanel from './AuthPanel'

export default function TelaCadastro({ cadastrar, entrar, voltar, carregando, erro }) {
  const [nome, setNome] = useState('')
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  return (
    <AuthPanel
      eyebrow="Novo jogador"
      title="Criar sua conta"
      description="Registre seu nome e mantenha sua identidade nos próximos desafios."
      footer={(
        <>
          <p>Já possui uma conta?</p>
          <button className="button-link" disabled={carregando} onClick={entrar}>Entrar</button>
          <button className="button-ghost auth-panel__back" disabled={carregando} onClick={voltar}>Voltar</button>
        </>
      )}
    >
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      <form className="auth-form" onSubmit={(evento) => {
        evento.preventDefault()
        if (!carregando) cadastrar(nome.trim(), email.trim(), senha)
      }}>
        <label htmlFor="cadastro-nome">Nome</label>
        <input id="cadastro-nome" autoComplete="name" required maxLength={100} value={nome} onChange={(e) => setNome(e.target.value)} disabled={carregando} />
        <label htmlFor="cadastro-email">E-mail</label>
        <input id="cadastro-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} disabled={carregando} />
        <label htmlFor="cadastro-senha">Senha (8 a 128 caracteres)</label>
        <input id="cadastro-senha" type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={senha} onChange={(e) => setSenha(e.target.value)} disabled={carregando} />
        <button className="auth-form__submit" disabled={carregando}>{carregando ? 'Cadastrando...' : 'Criar conta'}</button>
      </form>
    </AuthPanel>
  )
}
