import { useCallback, useEffect, useState } from 'react'
import { criarCatalogoInicialOficial, listarCatalogosOficiaisAdministrativos } from '../services/api'
import AdminRascunhos from './AdminRascunhos'

const rotuloModo = (modo) => modo === 'NEM_A_PATO' ? 'Nem a Pato' : 'Quiz Clássico'
const rotuloStatus = (status) => status.charAt(0) + status.slice(1).toLowerCase()
const formatarData = (data) => data
  ? new Date(data).toLocaleString('pt-BR')
  : 'Não registrada'

export default function AdminCatalogos({ aoExpirarSessao, aoAlterarFormulario }) {
  const [catalogos, setCatalogos] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)
  const [criando, setCriando] = useState(false)

  const atualizar = useCallback(() => {
    setErro('')
    setCarregando(true)
    setTentativa((valor) => valor + 1)
  }, [])

  useEffect(() => {
    let ativo = true
    listarCatalogosOficiaisAdministrativos().then((dados) => {
      if (!ativo) return
      setCatalogos(dados.catalogos)
      setErro('')
      setCarregando(false)
    }).catch((error) => {
      if (!ativo) return
      setCarregando(false)
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.status === 403
        ? 'Seu usuário não possui permissão para consultar catálogos oficiais.'
        : `Não foi possível carregar os catálogos. ${error.message}`)
    })
    return () => { ativo = false }
  }, [aoExpirarSessao, tentativa])

  const criarInicial = async (modo) => {
    const sugerido = modo === 'NEM_A_PATO' ? 'nem_a_pato_incremental' : 'quiz_classico_incremental'
    const catalogoId = window.prompt('Identificador técnico do catálogo inicial:', sugerido)
    if (!catalogoId?.trim() || !window.confirm('Criar e ativar uma versão inicial vazia para receber o primeiro rascunho?')) return
    setCriando(true); setErro('')
    try {
      await criarCatalogoInicialOficial({ catalogo_id: catalogoId.trim(), modo })
      atualizar()
    } catch (error) {
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.status === 409 ? 'Já existe um catálogo oficial para este modo.' : error.message)
    } finally { setCriando(false) }
  }

  return (
    <section className="admin-panel" aria-labelledby="admin-catalogos">
      <div className="admin-section-heading">
        <div>
          <span className="home-eyebrow">Versionados</span>
          <h2 id="admin-catalogos">Catálogos oficiais</h2>
        </div>
        <div className="admin-section-actions">
          {!carregando && !erro && <span>{catalogos.length} versões</span>}
          <button className="button-secondary" type="button" onClick={atualizar} disabled={carregando}>
            {carregando ? 'Atualizando…' : 'Atualizar catálogos'}
          </button>
        </div>
      </div>

      {carregando && (
        <div className="admin-loading" role="status" aria-live="polite">
          <span className="admin-loading__pulse" aria-hidden="true" />
          Carregando catálogos oficiais…
        </div>
      )}
      {erro && (
        <div className="admin-error" role="alert">
          <h3>Catálogos indisponíveis</h3>
          <p>{erro}</p>
          <button type="button" onClick={atualizar}>Tentar novamente</button>
        </div>
      )}
      {!carregando && !erro && !catalogos.length && (
        <div className="admin-empty"><p>Nenhum catálogo oficial cadastrado.</p><button type="button" disabled={criando} onClick={() => criarInicial('NEM_A_PATO')}>Criar catálogo inicial Nem a Pato</button></div>
      )}
      {!carregando && !erro && catalogos.length > 0 && (
        <div className="admin-grid admin-catalog-list">
          {catalogos.map((catalogo) => (
            <article key={catalogo.id} className="admin-catalog-card">
              <div className="admin-catalog-card__heading">
                <span className="admin-card-kicker">{rotuloModo(catalogo.modo)}</span>
                <span className={`admin-status admin-status--${catalogo.status_registro.toLowerCase()}`}>
                  {rotuloStatus(catalogo.status_registro)}
                </span>
              </div>
              <strong>{catalogo.catalogo_id.replaceAll('_', ' ')}</strong>
              <dl className="admin-catalog-details">
                <div><dt>Versão</dt><dd>{catalogo.versao}</dd></div>
                <div><dt>Perguntas</dt><dd>{catalogo.quantidade_perguntas.toLocaleString('pt-BR')}</dd></div>
                <div><dt>Estado editorial</dt><dd>{catalogo.estado_editorial ? rotuloStatus(catalogo.estado_editorial) : 'Não registrado separadamente'}</dd></div>
                <div><dt>Estado da versão</dt><dd>{rotuloStatus(catalogo.status_registro)}</dd></div>
                <div><dt>Criado em</dt><dd>{formatarData(catalogo.criado_em)}</dd></div>
                <div><dt>Ativado em</dt><dd>{formatarData(catalogo.ativado_em)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      )}
      {!carregando && !erro && (
        <AdminRascunhos catalogos={catalogos} aoExpirarSessao={aoExpirarSessao} aoAlterarFormulario={aoAlterarFormulario} />
      )}
      <p className="admin-note">Catálogos publicados permanecem somente leitura. Alterações são isoladas em rascunhos e não afetam os jogos.</p>
    </section>
  )
}
