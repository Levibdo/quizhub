import { useCallback, useEffect, useState } from 'react'
import { criarCatalogoInicialOficial, listarCatalogosOficiaisAdministrativos, reativarCatalogoOficial } from '../services/api'
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
  const [reativando, setReativando] = useState('')

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

  const reativar = async (catalogo) => {
    const ativo = catalogos.find((item) => item.modo === catalogo.modo && item.status_registro === 'ATIVO')
    if (!ativo || !catalogo.elegivel_reativacao) return
    const justificativa = window.prompt(
      `${rotuloModo(catalogo.modo)}: reativar a versão ${catalogo.versao} (${catalogo.quantidade_perguntas} perguntas) no lugar da versão ${ativo.versao}.\n\nInforme a justificativa administrativa:`,
    )
    if (!justificativa?.trim() || justificativa.trim().length < 10) return
    if (!window.confirm(`Confirmar a reativação da versão ${catalogo.versao}? A versão ${ativo.versao} será arquivada.`)) return
    setReativando(catalogo.id); setErro('')
    try {
      await reativarCatalogoOficial(catalogo.id, justificativa.trim(), ativo.id)
      atualizar()
    } catch (error) {
      if (error.status === 401) aoExpirarSessao()
      else if (error.status === 412) setErro('A versão ativa mudou. Atualize os catálogos e tente novamente.')
      else setErro(`Não foi possível reativar a versão. ${error.message}`)
    } finally { setReativando('') }
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
              {catalogo.elegivel_reativacao && catalogos.some((item) => item.modo === catalogo.modo && item.status_registro === 'ATIVO') && (
                <button className="button-secondary" type="button" disabled={Boolean(reativando)} onClick={() => reativar(catalogo)}>
                  {reativando === catalogo.id ? 'Reativando…' : 'Reativar esta versão'}
                </button>
              )}
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
