import { useEffect, useState } from 'react'
import { obterResumoAdministrativo } from '../services/api'

export default function TelaAdmin({ voltar, aoExpirarSessao }) {
  const [resumo, setResumo] = useState(null)
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)

  useEffect(() => {
    let ativo = true
    obterResumoAdministrativo().then((dados) => {
      if (ativo) { setResumo(dados); setErro('') }
    }).catch((error) => {
      if (!ativo) return
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.status === 403
        ? 'Seu usuário não possui permissão administrativa.'
        : `Não foi possível carregar o painel. ${error.message}`)
    })
    return () => { ativo = false }
  }, [aoExpirarSessao, tentativa])

  return (
    <section className="admin-screen" aria-labelledby="admin-title">
      <div className="admin-screen__heading">
        <span className="home-eyebrow">Área restrita</span>
        <h1 id="admin-title">Administração</h1>
        <p>Catálogos oficiais e trilha de operações sensíveis.</p>
      </div>

      {!resumo && !erro && <p role="status">Carregando dados administrativos...</p>}
      {erro && (
        <div className="admin-panel" role="alert">
          <p>{erro}</p>
          <button onClick={() => {
            setErro('')
            setResumo(null)
            setTentativa((valor) => valor + 1)
          }}>Tentar novamente</button>
        </div>
      )}
      {resumo && (
        <>
          <section className="admin-panel" aria-labelledby="admin-catalogos">
            <h2 id="admin-catalogos">Catálogos oficiais</h2>
            <div className="admin-grid">
              {resumo.catalogos.map((catalogo) => (
                <article key={catalogo.id} className="admin-catalog-card">
                  <strong>{catalogo.catalogo_id}</strong>
                  <span>{catalogo.modo.replaceAll('_', ' ')}</span>
                  <span>Versão {catalogo.versao}</span>
                  <span className={`admin-status admin-status--${catalogo.status.toLowerCase()}`}>
                    {catalogo.status}
                  </span>
                </article>
              ))}
              {!resumo.catalogos.length && <p>Nenhum catálogo cadastrado.</p>}
            </div>
          </section>
          <section className="admin-panel" aria-labelledby="admin-auditoria">
            <h2 id="admin-auditoria">Auditoria recente</h2>
            <div className="admin-audit-list">
              {resumo.auditorias.map((item) => (
                <article key={item.id}>
                  <strong>{item.operacao}</strong>
                  <span>{item.administrador_nome}</span>
                  <span>{item.resultado}</span>
                  <time dateTime={item.ocorrida_em}>{new Date(item.ocorrida_em).toLocaleString('pt-BR')}</time>
                </article>
              ))}
              {!resumo.auditorias.length && <p>Nenhuma operação administrativa registrada.</p>}
            </div>
          </section>
        </>
      )}
      <button className="button-secondary" onClick={voltar}>Voltar ao início</button>
    </section>
  )
}
