import { useState } from 'react'

export default function TelaCadastro({ cadastrar, entrar, voltar, carregando, erro }) {
  const [nome, setNome] = useState('')
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  return (
    <>
      <h1>Criar conta</h1>
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      <form className="form-jogador" onSubmit={(evento) => {
        evento.preventDefault()
        if (!carregando) cadastrar(nome.trim(), email.trim(), senha)
      }}>
        <label htmlFor="cadastro-nome">Nome</label>
        <input id="cadastro-nome" autoComplete="name" required maxLength={100} value={nome} onChange={(e) => setNome(e.target.value)} disabled={carregando} />
        <label htmlFor="cadastro-email">E-mail</label>
        <input id="cadastro-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} disabled={carregando} />
        <label htmlFor="cadastro-senha">Senha (8 a 128 caracteres)</label>
        <input id="cadastro-senha" type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={senha} onChange={(e) => setSenha(e.target.value)} disabled={carregando} />
        <button disabled={carregando}>{carregando ? 'Cadastrando...' : 'Criar conta'}</button>
      </form>
      <button disabled={carregando} onClick={entrar}>Já tenho uma conta / Entrar</button>
      <button disabled={carregando} onClick={voltar}>Voltar</button>
    </>
  )
}
