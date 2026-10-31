import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import {
  listarPerguntasOficiais,
  obterOpcoesPerguntasOficiais,
  obterPerguntaOficial,
} from '../services/api'

const FILTROS_INICIAIS = {
  busca: '', modo: '', catalogo_id: '', versao: '', categoria_id: '',
  ativa: '', dificuldade: '', limite: '20',
}

const rotuloModo = (modo) => modo === 'NEM_A_PATO' ? 'Nem a Pato' : 'Quiz Clássico'
const rotuloStatus = (ativa) => ativa ? 'Ativa' : 'Inativa'
const rotuloDificuldade = (valor) => ({
  FACIL: 'Fácil', MEDIA: 'Média', DIFICIL: 'Difícil',
}[valor] || 'Não informada')

function DetalhePergunta({ detalhe, carregando, erro, aoFechar, aoTentarNovamente }) {
  if (!detalhe && !carregando && !erro) return null
  return (
    <section className="admin-question-detail" aria-labelledby="admin-question-detail-title">
      <div className="admin-question-detail__heading">
        <div>
          <span className="home-eyebrow">Detalhes somente leitura</span>
          <h3 id="admin-question-detail-title">Pergunta oficial</h3>
        </div>
        <button type="button" className="button-secondary" onClick={aoFechar}>Fechar detalhes</button>
      </div>
      {carregando && <p role="status">Carregando detalhes da pergunta…</p>}
      {erro && <div className="admin-error" role="alert"><p>{erro}</p><button type="button" onClick={aoTentarNovamente}>Tentar novamente</button></div>}
      {detalhe && !erro && (
        <div className="admin-question-detail__body">
          <div className="admin-question-detail__meta">
            <span className="admin-card-kicker">{rotuloModo(detalhe.modo)}</span>
            <span>{detalhe.id_editorial || `ID ${detalhe.id}`}</span>
            <span>{detalhe.categoria.nome}</span>
            <span>{detalhe.catalogo.catalogo_id} · versão {detalhe.catalogo.versao}</span>
            <span className={`admin-status admin-status--${detalhe.ativa ? 'ativo' : 'inativo'}`}>{rotuloStatus(detalhe.ativa)}</span>
          </div>
          <h4>{detalhe.enunciado}</h4>
          {detalhe.modo === 'QUIZ_CLASSICO' ? (
            <ol className="admin-question-alternatives" type="A">
              {detalhe.alternativas.map((alternativa, indice) => (
                <li key={`${indice}-${alternativa}`} className={indice === detalhe.alternativa_correta ? 'is-correct' : ''}>
                  <span>{alternativa}</span>
                  {indice === detalhe.alternativa_correta && <strong>Resposta correta</strong>}
                </li>
              ))}
            </ol>
          ) : (
            <dl className="admin-question-answer">
              <div><dt>Resposta numérica</dt><dd>{detalhe.resposta_numerica}</dd></div>
              <div><dt>Unidade</dt><dd>{detalhe.unidade || 'Não informada'}</dd></div>
              <div><dt>Natureza</dt><dd>{detalhe.natureza_resposta || 'Não informada'}</dd></div>
              {detalhe.qualificacao_estimativa && <div><dt>Qualificação</dt><dd>{detalhe.qualificacao_estimativa}</dd></div>}
            </dl>
          )}
          <div className="admin-question-explanation"><strong>Explicação</strong><p>{detalhe.explicacao}</p></div>
          {detalhe.fonte_legada && (
            <div className="admin-question-sources">
              <strong>Fonte legada</strong>
              <p>{detalhe.fonte_legada.nome || 'Sem título'}</p>
              {detalhe.fonte_legada.url && <a href={detalhe.fonte_legada.url} target="_blank" rel="noreferrer">Abrir fonte legada</a>}
            </div>
          )}
          <div className="admin-question-sources">
            <strong>Referências editoriais</strong>
            {detalhe.referencias.length ? (
              <ul>{detalhe.referencias.map((fonte) => (
                <li key={`${fonte.url}-${fonte.acessada_em}`}><a href={fonte.url} target="_blank" rel="noreferrer">{fonte.titulo}</a><span>Acesso: {fonte.acessada_em}</span></li>
              ))}</ul>
            ) : <p>Nenhuma referência editorial registrada.</p>}
          </div>
        </div>
      )}
    </section>
  )
}

export default function AdminPerguntas({ aoExpirarSessao }) {
  const formularioId = useId()
  const [rascunho, setRascunho] = useState(FILTROS_INICIAIS)
  const [filtros, setFiltros] = useState(FILTROS_INICIAIS)
  const [pagina, setPagina] = useState(1)
  const [dados, setDados] = useState(null)
  const [opcoes, setOpcoes] = useState({ catalogos: [], categorias: [] })
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)
  const [selecaoDetalhe, setSelecaoDetalhe] = useState(null)
  const [detalhe, setDetalhe] = useState(null)
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false)
  const [erroDetalhe, setErroDetalhe] = useState('')
  const [tentativaDetalhe, setTentativaDetalhe] = useState(0)

  const carregar = useCallback(() => {
    setCarregando(true); setErro(''); setTentativa((valor) => valor + 1)
  }, [])

  useEffect(() => {
    let ativo = true
    Promise.all([
      listarPerguntasOficiais({ ...filtros, pagina }),
      obterOpcoesPerguntasOficiais(),
    ]).then(([resposta, filtrosDisponiveis]) => {
      if (!ativo) return
      setDados(resposta); setOpcoes(filtrosDisponiveis); setErro(''); setCarregando(false)
    }).catch((error) => {
      if (!ativo) return
      setCarregando(false)
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.status === 403
        ? 'Seu usuário não possui permissão para consultar perguntas oficiais.'
        : `Não foi possível carregar as perguntas. ${error.message}`)
    })
    return () => { ativo = false }
  }, [aoExpirarSessao, filtros, pagina, tentativa])

  useEffect(() => {
    if (!selecaoDetalhe) return undefined
    let ativo = true
    obterPerguntaOficial(selecaoDetalhe.modo, selecaoDetalhe.id).then((resposta) => {
      if (!ativo) return
      setDetalhe(resposta); setCarregandoDetalhe(false)
    }).catch((error) => {
      if (!ativo) return
      setCarregandoDetalhe(false)
      if (error.status === 401) aoExpirarSessao()
      else setErroDetalhe(error.status === 404
        ? 'A pergunta oficial não foi encontrada.'
        : `Não foi possível carregar os detalhes. ${error.message}`)
    })
    return () => { ativo = false }
  }, [aoExpirarSessao, selecaoDetalhe, tentativaDetalhe])

  const catalogosVisiveis = useMemo(() => opcoes.catalogos.filter(
    (item) => !rascunho.modo || item.modo === rascunho.modo,
  ), [opcoes.catalogos, rascunho.modo])
  const categoriasVisiveis = useMemo(() => opcoes.categorias.filter(
    (item) => !rascunho.modo || item.modo === rascunho.modo,
  ), [opcoes.categorias, rascunho.modo])
  const versoes = useMemo(() => [...new Set(catalogosVisiveis.map((item) => item.versao))].sort((a, b) => b - a), [catalogosVisiveis])

  const alterar = (evento) => {
    const { name, value } = evento.target
    setRascunho((atual) => ({
      ...atual, [name]: value,
      ...(name === 'modo' ? { catalogo_id: '', categoria_id: '', dificuldade: value === 'NEM_A_PATO' ? '' : atual.dificuldade } : {}),
    }))
  }
  const aplicar = (evento) => {
    evento.preventDefault(); setPagina(1); setCarregando(true); setErro(''); setFiltros({ ...rascunho })
  }
  const limpar = () => {
    setRascunho(FILTROS_INICIAIS); setFiltros(FILTROS_INICIAIS); setPagina(1); setCarregando(true); setErro('')
  }
  const abrirDetalhe = (item) => {
    setDetalhe(null); setErroDetalhe(''); setCarregandoDetalhe(true)
    setSelecaoDetalhe({ modo: item.modo, id: item.id })
  }
  const fecharDetalhe = () => { setSelecaoDetalhe(null); setDetalhe(null); setErroDetalhe('') }
  const tentarDetalheNovamente = () => {
    setErroDetalhe(''); setCarregandoDetalhe(true)
    setTentativaDetalhe((valor) => valor + 1)
  }

  return (
    <section className="admin-panel" aria-labelledby="admin-perguntas">
      <div className="admin-section-heading"><div><span className="home-eyebrow">Acervo versionado</span><h2 id="admin-perguntas">Perguntas oficiais</h2></div>{dados && !erro && <span>{dados.total.toLocaleString('pt-BR')} resultados</span>}</div>
      <form className="admin-question-filters" aria-label="Filtros de perguntas oficiais" onSubmit={aplicar}>
        <label htmlFor={`${formularioId}-busca`}>Pesquisar enunciado<input id={`${formularioId}-busca`} name="busca" value={rascunho.busca} onChange={alterar} maxLength="300" placeholder="Trecho da pergunta" /></label>
        <label htmlFor={`${formularioId}-modo`}>Modo<select id={`${formularioId}-modo`} name="modo" value={rascunho.modo} onChange={alterar}><option value="">Todos</option><option value="QUIZ_CLASSICO">Quiz Clássico</option><option value="NEM_A_PATO">Nem a Pato</option></select></label>
        <label htmlFor={`${formularioId}-catalogo`}>Catálogo<select id={`${formularioId}-catalogo`} name="catalogo_id" value={rascunho.catalogo_id} onChange={alterar}><option value="">Todos</option>{catalogosVisiveis.map((item) => <option key={item.id} value={item.id}>{item.catalogo_id} · v{item.versao}</option>)}</select></label>
        <label htmlFor={`${formularioId}-versao`}>Versão<select id={`${formularioId}-versao`} name="versao" value={rascunho.versao} onChange={alterar}><option value="">Todas</option>{versoes.map((versao) => <option key={versao} value={versao}>{versao}</option>)}</select></label>
        <label htmlFor={`${formularioId}-categoria`}>Categoria<select id={`${formularioId}-categoria`} name="categoria_id" value={rascunho.categoria_id} onChange={alterar}><option value="">Todas</option>{categoriasVisiveis.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></label>
        <label htmlFor={`${formularioId}-estado`}>Estado<select id={`${formularioId}-estado`} name="ativa" value={rascunho.ativa} onChange={alterar}><option value="">Todos</option><option value="true">Ativas</option><option value="false">Inativas</option></select></label>
        <label htmlFor={`${formularioId}-dificuldade`}>Dificuldade<select id={`${formularioId}-dificuldade`} name="dificuldade" value={rascunho.dificuldade} onChange={alterar} disabled={rascunho.modo === 'NEM_A_PATO'}><option value="">Todas</option><option value="FACIL">Fácil</option><option value="MEDIA">Média</option><option value="DIFICIL">Difícil</option></select></label>
        <label htmlFor={`${formularioId}-limite`}>Por página<select id={`${formularioId}-limite`} name="limite" value={rascunho.limite} onChange={alterar}><option value="10">10</option><option value="20">20</option><option value="50">50</option><option value="100">100</option></select></label>
        <div className="admin-question-filters__actions"><button type="submit" disabled={carregando}>Aplicar filtros</button><button type="button" className="button-secondary" onClick={limpar} disabled={carregando}>Limpar filtros</button></div>
      </form>

      {carregando && !dados && <div className="admin-loading" role="status">Carregando perguntas oficiais…</div>}
      {erro && <div className="admin-error" role="alert"><p>{erro}</p><button type="button" onClick={carregar}>Tentar novamente</button></div>}
      {dados && !erro && <>
        {carregando && <p role="status" className="admin-audit-updating">Atualizando resultados…</p>}
        <ol className="admin-question-list" aria-label="Perguntas oficiais">
          {dados.itens.map((item) => <li key={`${item.modo}-${item.id}`}><article className={`admin-question-card admin-question-card--${item.modo.toLowerCase()}`}>
            <div className="admin-question-card__heading"><div><span className="admin-card-kicker">{rotuloModo(item.modo)}</span><span>{item.id_editorial || `ID ${item.id}`}</span></div><span className={`admin-status admin-status--${item.ativa ? 'ativo' : 'inativo'}`}>{rotuloStatus(item.ativa)}</span></div>
            <h3>{item.enunciado}</h3>
            <div className="admin-question-card__meta"><span>{item.categoria.nome}</span><span>{item.catalogo.catalogo_id} · v{item.catalogo.versao}</span>{item.dificuldade && <span>{rotuloDificuldade(item.dificuldade)}</span>}</div>
            <button type="button" className="button-secondary" onClick={() => abrirDetalhe(item)}>Visualizar detalhes</button>
          </article></li>)}
        </ol>
        {!dados.itens.length && <p className="admin-empty">Nenhuma pergunta oficial corresponde aos filtros informados.</p>}
        <nav className="admin-pagination" aria-label="Paginação das perguntas oficiais"><button type="button" className="button-secondary" disabled={pagina <= 1 || carregando} onClick={() => { setPagina(pagina - 1); setCarregando(true) }}>Anterior</button><span>Página {dados.total_paginas ? pagina : 0} de {dados.total_paginas}</span><button type="button" className="button-secondary" disabled={pagina >= dados.total_paginas || carregando} onClick={() => { setPagina(pagina + 1); setCarregando(true) }}>Próxima</button></nav>
      </>}
      <DetalhePergunta detalhe={detalhe} carregando={carregandoDetalhe} erro={erroDetalhe} aoFechar={fecharDetalhe} aoTentarNovamente={tentarDetalheNovamente} />
      <p className="admin-note">Consulta somente leitura. Nenhuma pergunta ou catálogo é alterado nesta seção.</p>
    </section>
  )
}
