import { useCallback, useEffect, useId, useState } from 'react'
import { listarAuditoriasAdministrativas } from '../services/api'

const FILTROS_INICIAIS = {
  busca: '', operacao: '', administrador_id: '', resultado: '',
  inicio: '', fim: '', ordem: 'desc', limite: '20',
}

const rotuloResultado = (resultado) => ({
  SUCESSO: 'Sucesso', REJEITADA: 'Rejeitada', FALHA: 'Falha',
}[resultado] || resultado)

const formatarData = (data) => new Date(data).toLocaleString('pt-BR')

function paraIsoLocal(valor) {
  return valor ? new Date(valor).toISOString() : ''
}

function DetalhesEvento({ item }) {
  const linhas = Object.entries(item.detalhes || {})
  return (
    <details className="admin-audit-details">
      <summary>Ver detalhes seguros</summary>
      <dl>
        <div><dt>ID do evento</dt><dd>{item.id}</dd></div>
        <div><dt>ID do administrador</dt><dd>{item.administrador_id}</dd></div>
        <div><dt>Tipo do recurso</dt><dd>{item.recurso_tipo}</dd></div>
        <div><dt>Identificador</dt><dd>{item.recurso_id || 'Não informado'}</dd></div>
        {item.catalogo_id && <div><dt>Catálogo</dt><dd>{item.catalogo_id}</dd></div>}
        {item.catalogo_versao !== null && item.catalogo_versao !== undefined && (
          <div><dt>Versão</dt><dd>{item.catalogo_versao}</dd></div>
        )}
      </dl>
      {linhas.length > 0 && (
        <div className="admin-audit-details__metadata">
          <strong>Metadados sanitizados</strong>
          <pre>{JSON.stringify(item.detalhes, null, 2)}</pre>
        </div>
      )}
    </details>
  )
}

export default function AdminAuditoria({ aoExpirarSessao }) {
  const formularioId = useId()
  const [rascunho, setRascunho] = useState(FILTROS_INICIAIS)
  const [filtros, setFiltros] = useState(FILTROS_INICIAIS)
  const [pagina, setPagina] = useState(1)
  const [dados, setDados] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)

  const carregar = useCallback(() => {
    setCarregando(true)
    setErro('')
    setTentativa((valor) => valor + 1)
  }, [])

  useEffect(() => {
    let ativo = true
    const parametros = {
      ...filtros,
      pagina,
      inicio: paraIsoLocal(filtros.inicio),
      fim: paraIsoLocal(filtros.fim),
    }
    listarAuditoriasAdministrativas(parametros).then((resposta) => {
      if (!ativo) return
      setDados(resposta)
      setCarregando(false)
    }).catch((error) => {
      if (!ativo) return
      setCarregando(false)
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.status === 403
        ? 'Seu usuário não possui permissão para consultar a auditoria.'
        : `Não foi possível carregar a auditoria. ${error.message}`)
    })
    return () => { ativo = false }
  }, [aoExpirarSessao, filtros, pagina, tentativa])

  const alterar = (evento) => setRascunho((atual) => ({
    ...atual, [evento.target.name]: evento.target.value,
  }))
  const aplicar = (evento) => {
    evento.preventDefault()
    setCarregando(true)
    setErro('')
    setPagina(1)
    setFiltros({ ...rascunho })
    setTentativa((valor) => valor + 1)
  }
  const limpar = () => {
    setCarregando(true)
    setErro('')
    setRascunho(FILTROS_INICIAIS)
    setPagina(1)
    setFiltros(FILTROS_INICIAIS)
    setTentativa((valor) => valor + 1)
  }
  const mudarPagina = (proxima) => {
    setCarregando(true)
    setErro('')
    setPagina(proxima)
  }

  return (
    <section className="admin-panel" aria-labelledby="admin-auditoria">
      <div className="admin-section-heading">
        <div><span className="home-eyebrow">Rastreabilidade</span><h2 id="admin-auditoria">Auditoria administrativa</h2></div>
        {dados && <span>{dados.total.toLocaleString('pt-BR')} eventos</span>}
      </div>

      <form className="admin-audit-filters" aria-label="Filtros da auditoria" onSubmit={aplicar}>
        <label htmlFor={`${formularioId}-busca`}>Pesquisar recurso ou operação
          <input id={`${formularioId}-busca`} name="busca" value={rascunho.busca} onChange={alterar}
            maxLength="160" placeholder="ID, catálogo ou operação" />
        </label>
        <label htmlFor={`${formularioId}-operacao`}>Tipo de ação
          <input id={`${formularioId}-operacao`} name="operacao" value={rascunho.operacao} onChange={alterar}
            maxLength="80" placeholder="Ex.: IMPORTAR_PERGUNTAS" />
        </label>
        <label htmlFor={`${formularioId}-admin`}>ID do administrador
          <input id={`${formularioId}-admin`} name="administrador_id" value={rascunho.administrador_id}
            onChange={alterar} placeholder="UUID" />
        </label>
        <label htmlFor={`${formularioId}-resultado`}>Resultado
          <select id={`${formularioId}-resultado`} name="resultado" value={rascunho.resultado} onChange={alterar}>
            <option value="">Todos</option><option value="SUCESSO">Sucesso</option>
            <option value="REJEITADA">Rejeitada</option><option value="FALHA">Falha</option>
          </select>
        </label>
        <label htmlFor={`${formularioId}-inicio`}>A partir de
          <input id={`${formularioId}-inicio`} name="inicio" type="datetime-local" value={rascunho.inicio} onChange={alterar} />
        </label>
        <label htmlFor={`${formularioId}-fim`}>Até
          <input id={`${formularioId}-fim`} name="fim" type="datetime-local" value={rascunho.fim} onChange={alterar} />
        </label>
        <label htmlFor={`${formularioId}-ordem`}>Ordenação
          <select id={`${formularioId}-ordem`} name="ordem" value={rascunho.ordem} onChange={alterar}>
            <option value="desc">Mais recentes</option><option value="asc">Mais antigos</option>
          </select>
        </label>
        <label htmlFor={`${formularioId}-limite`}>Por página
          <select id={`${formularioId}-limite`} name="limite" value={rascunho.limite} onChange={alterar}>
            <option value="10">10</option><option value="20">20</option>
            <option value="50">50</option><option value="100">100</option>
          </select>
        </label>
        <div className="admin-audit-filters__actions">
          <button type="submit" disabled={carregando}>Aplicar filtros</button>
          <button type="button" className="button-secondary" onClick={limpar} disabled={carregando}>Limpar filtros</button>
        </div>
      </form>

      {carregando && !dados && <div className="admin-loading" role="status">Carregando eventos de auditoria…</div>}
      {erro && <div className="admin-error admin-audit-feedback" role="alert"><p>{erro}</p><button type="button" onClick={carregar}>Tentar novamente</button></div>}
      {dados && !erro && (
        <>
          {carregando && <p className="admin-audit-updating" role="status">Atualizando resultados…</p>}
          <ol className="admin-audit-events" aria-label="Eventos administrativos">
            {dados.itens.map((item) => (
              <li key={item.id}>
                <article>
                  <div className="admin-audit-event__heading">
                    <div><span className="admin-card-kicker">{item.recurso_tipo.replaceAll('_', ' ')}</span><h3>{item.operacao.replaceAll('_', ' ')}</h3></div>
                    <span className={`admin-status admin-status--${item.resultado.toLowerCase()}`}>{rotuloResultado(item.resultado)}</span>
                  </div>
                  <div className="admin-audit-event__summary">
                    <span><strong>Administrador</strong>{item.administrador_nome}</span>
                    <span><strong>Recurso</strong>{item.recurso_id || 'Não informado'}</span>
                    <time dateTime={item.ocorrida_em}><strong>Data e hora</strong>{formatarData(item.ocorrida_em)}</time>
                  </div>
                  <DetalhesEvento item={item} />
                </article>
              </li>
            ))}
          </ol>
          {!dados.itens.length && <p className="admin-empty">Nenhum evento corresponde aos filtros informados.</p>}
          <nav className="admin-pagination" aria-label="Paginação da auditoria">
            <button type="button" className="button-secondary" disabled={pagina <= 1 || carregando} onClick={() => mudarPagina(pagina - 1)}>Anterior</button>
            <span>Página {dados.total_paginas ? pagina : 0} de {dados.total_paginas}</span>
            <button type="button" className="button-secondary" disabled={pagina >= dados.total_paginas || carregando} onClick={() => mudarPagina(pagina + 1)}>Próxima</button>
          </nav>
        </>
      )}
    </section>
  )
}
