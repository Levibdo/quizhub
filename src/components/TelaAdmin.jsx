import { useCallback, useEffect, useState } from 'react'
import { obterDashboardAdministrativo } from '../services/api'
import AdminAuditoria from './AdminAuditoria'
import AdminCatalogos from './AdminCatalogos'
import AdminPerguntas from './AdminPerguntas'

const SECOES = [
  ['visao-geral', 'Visão geral'],
  ['catalogos', 'Catálogos oficiais'],
  ['perguntas', 'Perguntas oficiais'],
  ['temporadas', 'Temporadas'],
  ['usuarios', 'Usuários'],
  ['auditoria', 'Auditoria'],
]

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

export default function TelaAdmin({ voltar, aoExpirarSessao, registrarProtecaoNavegacao }) {
  const [dashboard, setDashboard] = useState(null)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(true)
  const [secao, setSecao] = useState('visao-geral')
  const [tentativa, setTentativa] = useState(0)
  const [formularioSujo, setFormularioSujo] = useState(false)

  const executarOuConfirmar = useCallback((acao) => {
    if (!formularioSujo || window.confirm('Descartar as alterações não salvas?')) acao()
  }, [formularioSujo])

  useEffect(() => {
    registrarProtecaoNavegacao?.((acao) => executarOuConfirmar(acao))
    return () => registrarProtecaoNavegacao?.(null)
  }, [executarOuConfirmar, registrarProtecaoNavegacao])

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
            onClick={() => executarOuConfirmar(() => setSecao(id))}>{rotulo}</button>
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
        <AdminCatalogos aoExpirarSessao={aoExpirarSessao} aoAlterarFormulario={setFormularioSujo} />
      )}

      {dashboard && !erro && secao === 'perguntas' && (
        <AdminPerguntas aoExpirarSessao={aoExpirarSessao} />
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
        <AdminAuditoria aoExpirarSessao={aoExpirarSessao} />
      )}

      <button className="button-secondary admin-back" onClick={() => executarOuConfirmar(voltar)}>Voltar ao início</button>
    </section>
  )
}
