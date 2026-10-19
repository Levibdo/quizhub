import { useState } from 'react'
import { CosmicEye } from '../CosmicSigil'

function SiteHeader({
  aoClicarMarca,
  usuario,
  tela,
  bloqueado = false,
  inicio,
  jogos,
  ranking,
  entrar,
  cadastrar,
  meuConteudo,
  administrar,
  sair,
}) {
  const [menuAberto, setMenuAberto] = useState(false)
  const navegar = (acao) => () => {
    setMenuAberto(false)
    acao?.()
  }

  return (
    <header className="site-header">
      <div className="site-header__inner">
        <a className="site-brand" href="/" aria-label="QuizHub — ir para a página inicial" onClick={aoClicarMarca}>
          <span className="site-brand__mark" aria-hidden="true">
            <svg className="cosmic-eye-logo" viewBox="40 65 160 112" focusable="false">
              <CosmicEye />
            </svg>
          </span>
          <span className="site-brand__name">QUIZHUB</span>
        </a>

        <button
          className="site-menu-toggle"
          type="button"
          aria-expanded={menuAberto}
          aria-controls="site-navigation"
          onClick={() => setMenuAberto((aberto) => !aberto)}
        >
          <span className="site-menu-toggle__icon" aria-hidden="true"><i /><i /><i /></span>
          <span>{menuAberto ? 'Fechar' : 'Menu'}</span>
        </button>

        <nav
          id="site-navigation"
          className={`site-navigation${menuAberto ? ' site-navigation--open' : ''}`}
          aria-label="Navegação principal"
        >
          <div className="site-navigation__links">
            <button className="site-navigation__link" type="button" aria-current={tela === 'inicio' ? 'page' : undefined} disabled={bloqueado} onClick={navegar(inicio)}>Início</button>
            <button className="site-navigation__link" type="button" aria-current={tela === 'jogos' ? 'page' : undefined} disabled={bloqueado} onClick={navegar(jogos)}>Jogos</button>
            <button className="site-navigation__link" type="button" aria-current={tela === 'ranking' ? 'page' : undefined} disabled={bloqueado} onClick={navegar(ranking)}>Ranking</button>
            {usuario ? (
              <>
                <button className="site-navigation__link" type="button" aria-current={tela === 'meu-conteudo' ? 'page' : undefined} disabled={bloqueado} onClick={navegar(meuConteudo)}>Meu Conteúdo</button>
                {usuario.perfil === 'ADMIN' && (
                  <button className="site-navigation__link site-navigation__link--admin" type="button" aria-current={tela === 'admin' ? 'page' : undefined} disabled={bloqueado} onClick={navegar(administrar)}>Administração</button>
                )}
              </>
            ) : (
              <>
                <button className="site-navigation__link" type="button" aria-current={tela === 'login' ? 'page' : undefined} disabled={bloqueado} onClick={navegar(entrar)}>Entrar</button>
                <button className="site-navigation__cta" type="button" aria-current={tela === 'cadastro' ? 'page' : undefined} disabled={bloqueado} onClick={navegar(cadastrar)}>Criar conta</button>
              </>
            )}
          </div>

          {usuario && (
            <div className="site-session" aria-label={`Sessão ativa: ${usuario.nome}`}>
              <span className="site-session__presence" aria-hidden="true" />
              <span className="site-session__identity">
                <span className="site-session__label">Sessão ativa</span>
                <strong title={usuario.nome}>{usuario.nome}</strong>
              </span>
              <button className="site-session__logout" type="button" disabled={bloqueado} onClick={navegar(sair)}>Sair</button>
            </div>
          )}
        </nav>
      </div>
    </header>
  )
}

export default SiteHeader
