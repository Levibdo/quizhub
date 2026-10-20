import { useCallback, useEffect, useState } from 'react'
import { obterDashboardAdministrativo } from '../services/api'

const SECOES = [
  ['visao-geral', 'Visão geral'],
  ['catalogos', 'Catálogos oficiais'],
  ['perguntas', 'Perguntas oficiais'],
  ['temporadas', 'Temporadas'],
  ['usuarios', 'Usuários'],
  ['auditoria', 'Auditoria'],
]

const rotuloModo = (modo) => modo === 'NEM_A_PATO' ? 'Nem a Pato' : 'Quiz Clássico'
const rotuloStatus = (status) => status.charAt(0) + status.slice(1).toLowerCase()
const formatarData = (data) => new Date(data).toLocaleString('pt-BR')

function CartaoIndicador({ rotulo, valor, detalhe }) {
  return (
    <article className="admin-metric-card">
      <span>{rotulo}</span>
      <strong>{valor.toLocaleString('pt-BR')}</strong>
      {detalhe && <small>{detalhe}</small>}
    </article>
  )
}

function EstadoVazio({ children }) {
  return <p className="admin-empty">{children}</p>
}

export default function TelaAdmin({ voltar, aoExpirarSessao }) {
  const [dashboard, setDashboard] = useState(null)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(true)
  const [secao, setSecao] = useState('visao-geral')
  const [tentativa, setTentativa] = useState(0)

  const atualizar = useCallback(() => {
    setErro('')
    setCarregando(true)
    setTentativa((valor) => valor + 1)
  }, [])

  useEffect(() => {
    let ativo = true
    obterDashboardAdministrativo().then((dados) => {
      if (ativo) { setDashboard(dados); setErro(''); setCarregando(false) }
    }).catch((error) => {
      if (!ativo) return
      setCarregando(false)
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.status === 403
        ? 'Seu usuário não possui permissão administrativa.'
        : `Não foi possível carregar o painel. ${error.message}`)
    })
    return () => { ativo = false }
  }, [aoExpirarSessao, tentativa])

  const indicadores = dashboard?.indicadores

  return (
    <section className="admin-screen" aria-labelledby="admin-title">
      <header className="admin-screen__heading">
        <div>
          <span className="home-eyebrow">Área restrita</span>
          <h1 id="admin-title">Administração</h1>
          <p>Visão operacional do QuizHub, sem alterar dados.</p>
        </div>
        <button className="button-secondary admin-refresh" onClick={atualizar} disabled={carregando}>
          {carregando ? 'Atualizando…' : 'Atualizar dados'}
        </button>
      </header>

      <nav className="admin-navigation" aria-label="Seções administrativas">
        {SECOES.map(([id, rotulo]) => (
          <button key={id} type="button" aria-current={secao === id ? 'page' : undefined}
            onClick={() => setSecao(id)}>{rotulo}</button>
        ))}
      </nav>

      {carregando && !dashboard && (
        <div className="admin-loading" role="status" aria-live="polite">
          <span className="admin-loading__pulse" aria-hidden="true" />
          Carregando indicadores administrativos…
        </div>
      )}
      {erro && (
        <div className="admin-panel admin-error" role="alert">
          <h2>Dados indisponíveis</h2>
          <p>{erro}</p>
          <button onClick={atualizar}>Tentar novamente</button>
        </div>
      )}

      {dashboard && !erro && secao === 'visao-geral' && (
        <section className="admin-panel" aria-labelledby="admin-visao-geral">
          <div className="admin-section-heading">
            <div><span className="home-eyebrow">Agora</span><h2 id="admin-visao-geral">Visão geral</h2></div>
            {carregando && <span role="status">Atualizando…</span>}
          </div>
          <div className="admin-metrics">
            <CartaoIndicador rotulo="Usuários" valor={indicadores.usuarios.total}
              detalhe={`${indicadores.usuarios.ativos} ativos`} />
            <CartaoIndicador rotulo="Partidas" valor={indicadores.partidas.total}
              detalhe={`${indicadores.partidas.concluidas} concluídas`} />
            <CartaoIndicador rotulo="Perguntas oficiais" valor={indicadores.perguntas.oficiais} />
            <CartaoIndicador rotulo="Perguntas privadas" valor={indicadores.perguntas.privadas} />
            <CartaoIndicador rotulo="Categorias oficiais" valor={indicadores.categorias.oficiais} />
            <CartaoIndicador rotulo="Categorias privadas" valor={indicadores.categorias.privadas} />
            <CartaoIndicador rotulo="Catálogos ativos" valor={indicadores.catalogos_oficiais_ativos} />
          </div>
          <div className="admin-mode-summary" aria-label="Partidas por modo">
            <article><strong>Quiz Clássico</strong><span>{indicadores.partidas.quiz_classico.total} partidas</span><small>{indicadores.partidas.quiz_classico.concluidas} concluídas</small></article>
            <article><strong>Nem a Pato</strong><span>{indicadores.partidas.nem_a_pato.total} partidas</span><small>{indicadores.partidas.nem_a_pato.concluidas} concluídas</small></article>
          </div>
        </section>
      )}

      {dashboard && !erro && secao === 'catalogos' && (
        <section className="admin-panel" aria-labelledby="admin-catalogos">
          <div className="admin-section-heading"><div><span className="home-eyebrow">Versionados</span><h2 id="admin-catalogos">Catálogos oficiais</h2></div><span>{dashboard.catalogos.length} versões</span></div>
          <div className="admin-grid">
            {dashboard.catalogos.map((catalogo) => (
              <article key={catalogo.id} className="admin-catalog-card">
                <span className="admin-card-kicker">{rotuloModo(catalogo.modo)}</span>
                <strong>{catalogo.catalogo_id.replaceAll('_', ' ')}</strong>
                <span>Versão {catalogo.versao}</span>
                <span className={`admin-status admin-status--${catalogo.status.toLowerCase()}`}>
                  {rotuloStatus(catalogo.status)}
                </span>
              </article>
            ))}
          </div>
          {!dashboard.catalogos.length && <EstadoVazio>Nenhum catálogo oficial cadastrado.</EstadoVazio>}
        </section>
      )}

      {dashboard && !erro && secao === 'perguntas' && (
        <section className="admin-panel" aria-labelledby="admin-perguntas">
          <span className="home-eyebrow">Inventário</span><h2 id="admin-perguntas">Perguntas oficiais</h2>
          <p>Este resumo apresenta somente quantidades. O conteúdo privado dos jogadores não é exibido.</p>
          <div className="admin-metrics admin-metrics--compact">
            <CartaoIndicador rotulo="Oficiais" valor={indicadores.perguntas.oficiais} />
            <CartaoIndicador rotulo="Privadas" valor={indicadores.perguntas.privadas} detalhe="Não excluídas" />
            <CartaoIndicador rotulo="Total atual" valor={indicadores.perguntas.total} />
          </div>
          <p className="admin-note">A edição e publicação versionada serão disponibilizadas em uma etapa futura.</p>
        </section>
      )}

      {dashboard && !erro && secao === 'temporadas' && (
        <section className="admin-panel" aria-labelledby="admin-temporadas">
          <span className="home-eyebrow">Classificação</span><h2 id="admin-temporadas">Temporadas</h2>
          {dashboard.temporada_ativa ? (
            <article className="admin-season-card">
              <span className="admin-status admin-status--ativo">Ativa</span>
              <strong>{dashboard.temporada_ativa.nome}</strong>
              <span>Temporada {dashboard.temporada_ativa.numero}</span>
              <small>Início: {formatarData(dashboard.temporada_ativa.inicia_em)}</small>
            </article>
          ) : <EstadoVazio>Nenhuma temporada ativa no momento.</EstadoVazio>}
          <p className="admin-note">Esta etapa não permite iniciar, encerrar ou alterar temporadas.</p>
        </section>
      )}

      {dashboard && !erro && secao === 'usuarios' && (
        <section className="admin-panel" aria-labelledby="admin-usuarios">
          <span className="home-eyebrow">Contas</span><h2 id="admin-usuarios">Usuários</h2>
          <div className="admin-metrics admin-metrics--compact">
            <CartaoIndicador rotulo="Total" valor={indicadores.usuarios.total} />
            <CartaoIndicador rotulo="Ativos" valor={indicadores.usuarios.ativos} />
            <CartaoIndicador rotulo="Inativos" valor={indicadores.usuarios.total - indicadores.usuarios.ativos} />
          </div>
          <p className="admin-note">Nomes, e-mails e outros dados pessoais não são exibidos neste resumo.</p>
        </section>
      )}

      {dashboard && !erro && secao === 'auditoria' && (
        <section className="admin-panel" aria-labelledby="admin-auditoria">
          <span className="home-eyebrow">Rastreabilidade</span>
          <h2 id="admin-auditoria">Auditoria recente</h2>
          <div className="admin-audit-list">
            {dashboard.auditorias.map((item) => (
              <article key={item.id}>
                <strong>{item.operacao.replaceAll('_', ' ')}</strong>
                <span>{item.administrador_nome}</span>
                <span className={`admin-status admin-status--${item.resultado.toLowerCase()}`}>
                  {rotuloStatus(item.resultado)}
                </span>
                <time dateTime={item.ocorrida_em}>{formatarData(item.ocorrida_em)}</time>
              </article>
            ))}
            {!dashboard.auditorias.length && <EstadoVazio>Nenhuma operação administrativa registrada.</EstadoVazio>}
          </div>
        </section>
      )}

      <button className="button-secondary admin-back" onClick={voltar}>Voltar ao início</button>
    </section>
  )
}
