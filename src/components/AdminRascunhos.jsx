import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  confirmarImportacaoCatalogoJson,
  criarRascunhoOficial, descartarRascunhoOficial, listarHistoricoRascunho,
  listarCategoriasRascunho, listarPerguntasRascunho, listarRascunhosOficiais,
  obterPerguntaRascunho, obterRascunhoOficial, removerPerguntaRascunho,
  previsualizarImportacaoCatalogoJson, restaurarPerguntaRascunho,
  removerCategoriaRascunho, restaurarCategoriaRascunho,
  salvarCategoriaRascunho, salvarPerguntaRascunho, validarRascunhoOficial,
} from '../services/api'
import AdminRevisaoRascunho from './AdminRevisaoRascunho'

const VAZIA = { titulo: '', url: '', acessada_em: '' }
const MAX_BIGINT = '9223372036854775807'
const rotuloModo = (modo) => modo === 'NEM_A_PATO' ? 'Nem a Pato' : 'Quiz Clássico'
const formatarData = (valor) => valor ? new Date(valor).toLocaleString('pt-BR') : 'Não registrada'
const ROTULOS_NIVEL = { ERRO: 'Erros', AVISO: 'Avisos', INFORMACAO: 'Informações' }

function GestaoCategorias({ rascunho, categorias, aoAtualizar, aoErro }) {
  const [aberto, setAberto] = useState(false)
  const [editando, setEditando] = useState(null)
  const [formulario, setFormulario] = useState({ slug: '', nome: '', descricao: '', ativa: true })
  const iniciar = (item = null) => {
    setEditando(item); setFormulario(item ? { slug: item.slug, nome: item.nome, descricao: item.descricao || '', ativa: item.ativa } : { slug: '', nome: '', descricao: '', ativa: true }); setAberto(true)
  }
  const salvar = async (evento) => {
    evento.preventDefault()
    try {
      await salvarCategoriaRascunho(rascunho.id, editando?.categoria_id, { ...formulario, slug: formulario.slug.trim().toLowerCase(), nome: formulario.nome.trim(), descricao: formulario.descricao.trim() || null }, rascunho.revisao)
      setAberto(false); await aoAtualizar()
    } catch (error) { aoErro(error) }
  }
  const mudarEstado = async (item, restaurar) => {
    const acao = restaurar ? 'restaurar' : 'remover'
    if (!restaurar && !window.confirm(`Remover a categoria ${item.nome} deste rascunho?`)) return
    try {
      const executar = restaurar ? restaurarCategoriaRascunho : removerCategoriaRascunho
      await executar(rascunho.id, item.categoria_id, rascunho.revisao)
      await aoAtualizar()
    } catch (error) { aoErro(new Error(`Não foi possível ${acao} a categoria. ${error.message}`)) }
  }
  return <section className="admin-draft-categories" aria-labelledby="draft-categories-title">
    <div className="admin-section-heading"><div><span className="admin-draft-badge">IDENTIDADES VERSIONADAS</span><h4 id="draft-categories-title">Categorias deste rascunho</h4></div>{rascunho.status === 'EM_EDICAO' && <button type="button" onClick={() => iniciar()}>Adicionar categoria</button>}</div>
    {!categorias.length ? <p className="admin-empty">Nenhuma categoria definida.</p> : <div className="admin-category-list">{categorias.map((item) => <article key={item.id}><div><strong>{item.nome}</strong><span className="admin-status">{item.tipo_alteracao}</span></div><code>{item.slug}</code>{item.descricao && <p>{item.descricao}</p>}{rascunho.status === 'EM_EDICAO' && <div className="admin-draft-editor__actions">{item.tipo_alteracao === 'REMOVIDA' ? <button type="button" className="button-secondary" onClick={() => mudarEstado(item, true)}>Restaurar</button> : <><button type="button" className="button-secondary" onClick={() => iniciar(item)}>Editar no rascunho</button><button type="button" className="button-danger" onClick={() => mudarEstado(item, false)}>Remover</button></>}</div>}</article>)}</div>}
    {aberto && <form className="admin-draft-form-grid" onSubmit={salvar}><label>Slug<input value={formulario.slug} pattern="[a-z0-9][a-z0-9-]*" required onChange={(e) => setFormulario({ ...formulario, slug: e.target.value })} /></label><label>Nome<input value={formulario.nome} required onChange={(e) => setFormulario({ ...formulario, nome: e.target.value })} /></label><label className="admin-draft-span">Descrição<textarea value={formulario.descricao} onChange={(e) => setFormulario({ ...formulario, descricao: e.target.value })} /></label><div className="admin-draft-editor__actions"><button type="button" className="button-secondary" onClick={() => setAberto(false)}>Cancelar</button><button type="submit">Salvar categoria</button></div></form>}
  </section>
}

function ImportacaoJson({ catalogos, aoConcluir, aoErro }) {
  const [catalogoId, setCatalogoId] = useState('')
  const [conteudo, setConteudo] = useState(null)
  const [previa, setPrevia] = useState(null)
  const selecionar = async (evento) => {
    setPrevia(null); setConteudo(null)
    try { const texto = await evento.target.files?.[0]?.text(); if (texto) setConteudo(JSON.parse(texto)) }
    catch { aoErro(new Error('O arquivo não contém JSON válido.')) }
  }
  const previsualizar = async () => { try { setPrevia(await previsualizarImportacaoCatalogoJson(catalogoId, conteudo)) } catch (error) { aoErro(error) } }
  const confirmar = async () => { if (!window.confirm('Criar um rascunho com este conteúdo? Nada será publicado automaticamente.')) return; try { await confirmarImportacaoCatalogoJson(catalogoId, conteudo, previa.sha256); setConteudo(null); setPrevia(null); await aoConcluir() } catch (error) { aoErro(error) } }
  return <section className="admin-import-json"><h4>Importar catálogo JSON</h4><p className="admin-note">A importação cria um rascunho sujeito a validação, revisão e aprovação. Ela nunca publica automaticamente.</p><div className="admin-draft-filters"><label>Catálogo-base<select value={catalogoId} onChange={(e) => setCatalogoId(e.target.value)}><option value="">Selecione</option>{catalogos.filter((item) => item.status_registro === 'ATIVO').map((item) => <option key={item.id} value={item.id}>{rotuloModo(item.modo)} · v{item.versao}</option>)}</select></label><label>Arquivo JSON<input type="file" accept="application/json,.json" onChange={selecionar} /></label><button type="button" disabled={!catalogoId || !conteudo} onClick={previsualizar}>Pré-visualizar</button></div>{previa && <div className={previa.valido ? 'admin-success' : 'admin-error'} role="status"><p>{previa.total_categorias} categorias · {previa.total_perguntas} perguntas · {previa.valido ? 'estrutura válida' : `${previa.erros.length} erro(s)`}</p>{previa.erros.map((erro) => <p key={`${erro.registro}-${erro.campo}`}>Registro {erro.registro + 1}: {erro.campo} — {erro.codigo}</p>)}{previa.valido && <button type="button" onClick={confirmar}>Confirmar criação do rascunho</button>}</div>}</section>
}

function erroOperacao(error) {
  if (error.status === 412) return 'Este rascunho foi alterado por outro administrador. Suas alterações locais foram preservadas.'
  if (error.status === 409) return `A operação entrou em conflito. ${error.message}`
  if (error.status === 428) return 'A revisão do rascunho é obrigatória. Atualize o estado e tente novamente.'
  return error.message
}

function criarFormulario(modo, pergunta, categoriaId = '') {
  const base = pergunta || {}
  return {
    id_editorial: base.id_editorial || '', categoria_id: base.categoria_id || categoriaId,
    enunciado: base.enunciado || '', explicacao: base.explicacao || '', ativa: base.ativa ?? true,
    alternativas: base.alternativas || ['', '', '', ''], alternativa_correta: base.alternativa_correta ?? 0,
    dificuldade: base.dificuldade || 'MEDIA', resposta_numerica: base.resposta_numerica || '',
    unidade: base.unidade || '', fonte: base.fonte || '', fonte_url: base.fonte_url || '',
    fonte_acessada_em: base.fonte_acessada_em || '', tema_editorial: base.tema_editorial || '',
    natureza_resposta: base.natureza_resposta || 'EXATA',
    qualificacao_estimativa: base.qualificacao_estimativa || '',
    referencias: base.referencias?.length ? base.referencias : [{ ...VAZIA }], modo,
  }
}

function validar(formulario) {
  const erros = {}
  if (!formulario.id_editorial.trim()) erros.id_editorial = 'Informe o ID editorial.'
  if (!formulario.categoria_id) erros.categoria_id = 'Selecione a categoria.'
  if (!formulario.enunciado.trim()) erros.enunciado = 'Informe o enunciado.'
  if (!formulario.explicacao.trim()) erros.explicacao = 'Informe a explicação.'
  if (formulario.modo === 'QUIZ_CLASSICO' && formulario.alternativas.some((item) => !item.trim())) {
    erros.alternativas = 'Preencha as quatro alternativas.'
  }
  if (formulario.modo === 'NEM_A_PATO') {
    const numero = formulario.resposta_numerica.trim()
    if (!/^\d+$/.test(numero) || numero.length > MAX_BIGINT.length ||
      (numero.length === MAX_BIGINT.length && numero > MAX_BIGINT)) {
      erros.resposta_numerica = `Informe um inteiro entre 0 e ${MAX_BIGINT}.`
    }
  }
  if (!formulario.referencias.length || formulario.referencias.some(
    (fonte) => !fonte.titulo.trim() || !fonte.url.trim() || !fonte.acessada_em,
  )) erros.referencias = 'Cada referência precisa de título, URL e data de acesso.'
  return erros
}

function payloadFormulario(formulario) {
  const comum = {
    id_editorial: formulario.id_editorial.trim(), categoria_id: formulario.categoria_id,
    enunciado: formulario.enunciado.trim(), explicacao: formulario.explicacao.trim(),
    ativa: formulario.ativa,
    referencias: formulario.referencias.map((fonte) => ({
      titulo: fonte.titulo.trim(), url: fonte.url.trim(), acessada_em: fonte.acessada_em,
    })),
  }
  if (formulario.modo === 'QUIZ_CLASSICO') return {
    ...comum, alternativas: formulario.alternativas.map((item) => item.trim()),
    alternativa_correta: Number(formulario.alternativa_correta), dificuldade: formulario.dificuldade,
  }
  return {
    ...comum, resposta_numerica: formulario.resposta_numerica.replace(/^0+(?=\d)/, ''),
    unidade: formulario.unidade || null, fonte: formulario.fonte || null,
    fonte_url: formulario.fonte_url || null, fonte_acessada_em: formulario.fonte_acessada_em || null,
    tema_editorial: formulario.tema_editorial || null,
    natureza_resposta: formulario.natureza_resposta,
    qualificacao_estimativa: formulario.qualificacao_estimativa || null,
  }
}

function EditorPergunta({ rascunho, pergunta, categorias, aoCancelar, aoSalvar, aoAlterarSujo, somenteLeitura = false }) {
  const [formulario, setFormulario] = useState(() => criarFormulario(
    rascunho.modo, pergunta, categorias[0]?.id,
  ))
  const [inicial] = useState(() => JSON.stringify(formulario))
  const [erros, setErros] = useState({})
  const [salvando, setSalvando] = useState(false)
  const [mensagem, setMensagem] = useState('')
  const alterado = JSON.stringify(formulario) !== inicial

  useEffect(() => {
    if (!alterado) return undefined
    const impedir = (evento) => { evento.preventDefault(); evento.returnValue = '' }
    window.addEventListener('beforeunload', impedir)
    return () => window.removeEventListener('beforeunload', impedir)
  }, [alterado])
  useEffect(() => {
    aoAlterarSujo?.(alterado && !somenteLeitura)
    return () => aoAlterarSujo?.(false)
  }, [alterado, aoAlterarSujo, somenteLeitura])

  const atualizar = (campo, valor) => setFormulario((atual) => ({ ...atual, [campo]: valor }))
  const cancelar = () => {
    if (!alterado || window.confirm('Descartar as alterações não salvas?')) aoCancelar()
  }
  const salvar = async (evento) => {
    evento.preventDefault()
    const encontrados = validar(formulario)
    setErros(encontrados)
    if (Object.keys(encontrados).length) {
      document.getElementById(`draft-${Object.keys(encontrados)[0]}`)?.focus()
      return
    }
    setSalvando(true); setMensagem('')
    try {
      await aoSalvar(payloadFormulario(formulario), pergunta?.id)
    } catch (error) {
      setMensagem(erroOperacao(error))
    } finally { setSalvando(false) }
  }
  const alterarFonte = (indice, campo, valor) => atualizar('referencias', formulario.referencias.map(
    (fonte, atual) => atual === indice ? { ...fonte, [campo]: valor } : fonte,
  ))
  const moverFonte = (indice, direcao) => {
    const destino = indice + direcao
    if (destino < 0 || destino >= formulario.referencias.length) return
    const fontes = [...formulario.referencias]
    ;[fontes[indice], fontes[destino]] = [fontes[destino], fontes[indice]]
    atualizar('referencias', fontes)
  }

  return (
    <form className="admin-draft-editor" onSubmit={salvar} noValidate>
      <div className="admin-draft-editor__heading">
        <div><span className="admin-draft-badge">RASCUNHO — NÃO PUBLICADO</span><h3>{somenteLeitura ? 'Visualizar pergunta' : pergunta ? 'Editar pergunta' : 'Adicionar pergunta'}</h3></div>
        <span aria-live="polite">{somenteLeitura ? 'Consulta somente leitura' : alterado ? 'Alterações não salvas' : 'Sem alterações pendentes'}</span>
      </div>
      {mensagem && <p className="admin-error" role="alert">{mensagem}</p>}
      <fieldset className="admin-draft-editor__readonly-group" disabled={somenteLeitura}>
      <div className="admin-draft-form-grid">
        <label>ID editorial<input id="draft-id_editorial" value={formulario.id_editorial} disabled={Boolean(pergunta)} onChange={(e) => atualizar('id_editorial', e.target.value)} aria-invalid={Boolean(erros.id_editorial)} />{erros.id_editorial && <small>{erros.id_editorial}</small>}</label>
        <label>Categoria<select id="draft-categoria_id" value={formulario.categoria_id} onChange={(e) => atualizar('categoria_id', e.target.value)} aria-invalid={Boolean(erros.categoria_id)}><option value="">Selecione</option>{categorias.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}</select>{erros.categoria_id && <small>{erros.categoria_id}</small>}</label>
        <label className="admin-draft-span">Enunciado<textarea id="draft-enunciado" value={formulario.enunciado} onChange={(e) => atualizar('enunciado', e.target.value)} aria-invalid={Boolean(erros.enunciado)} />{erros.enunciado && <small>{erros.enunciado}</small>}</label>
        {rascunho.modo === 'QUIZ_CLASSICO' ? <>
          {formulario.alternativas.map((alternativa, indice) => <label key={indice}>Alternativa {indice + 1}<input value={alternativa} onChange={(e) => atualizar('alternativas', formulario.alternativas.map((item, atual) => atual === indice ? e.target.value : item))} /></label>)}
          {erros.alternativas && <p className="admin-field-error admin-draft-span" role="alert">{erros.alternativas}</p>}
          <label>Resposta correta<select value={formulario.alternativa_correta} onChange={(e) => atualizar('alternativa_correta', e.target.value)}>{formulario.alternativas.map((_, indice) => <option key={indice} value={indice}>Alternativa {indice + 1}</option>)}</select></label>
          <label>Dificuldade<select value={formulario.dificuldade} onChange={(e) => atualizar('dificuldade', e.target.value)}><option value="FACIL">Fácil</option><option value="MEDIA">Média</option><option value="DIFICIL">Difícil</option></select></label>
        </> : <>
          <label>Resposta numérica<input id="draft-resposta_numerica" inputMode="numeric" value={formulario.resposta_numerica} onChange={(e) => atualizar('resposta_numerica', e.target.value)} aria-invalid={Boolean(erros.resposta_numerica)} />{erros.resposta_numerica && <small>{erros.resposta_numerica}</small>}</label>
          <label>Unidade<input value={formulario.unidade} onChange={(e) => atualizar('unidade', e.target.value)} /></label>
          <label>Natureza<select value={formulario.natureza_resposta} onChange={(e) => atualizar('natureza_resposta', e.target.value)}><option value="EXATA">Exata</option><option value="ESTIMATIVA">Estimativa</option></select></label>
          <label>Tema editorial<input value={formulario.tema_editorial} onChange={(e) => atualizar('tema_editorial', e.target.value)} /></label>
          <label className="admin-draft-span">Qualificação da estimativa<textarea value={formulario.qualificacao_estimativa} onChange={(e) => atualizar('qualificacao_estimativa', e.target.value)} /></label>
          <label>Fonte legada<input value={formulario.fonte} onChange={(e) => atualizar('fonte', e.target.value)} /></label>
          <label>URL da fonte legada<input type="url" value={formulario.fonte_url} onChange={(e) => atualizar('fonte_url', e.target.value)} /></label>
          <label>Data da fonte legada<input type="date" value={formulario.fonte_acessada_em} onChange={(e) => atualizar('fonte_acessada_em', e.target.value)} /></label>
        </>}
        <label className="admin-draft-span">Explicação<textarea id="draft-explicacao" value={formulario.explicacao} onChange={(e) => atualizar('explicacao', e.target.value)} aria-invalid={Boolean(erros.explicacao)} />{erros.explicacao && <small>{erros.explicacao}</small>}</label>
        <label className="admin-draft-check"><input type="checkbox" checked={formulario.ativa} onChange={(e) => atualizar('ativa', e.target.checked)} /> Pergunta ativa no futuro catálogo</label>
      </div>
      <fieldset className="admin-draft-sources"><legend>Referências editoriais</legend>
        {formulario.referencias.map((fonte, indice) => <div key={indice} className="admin-draft-source">
          <label>Título<input id={indice === 0 ? 'draft-referencias' : undefined} value={fonte.titulo} onChange={(e) => alterarFonte(indice, 'titulo', e.target.value)} /></label>
          <label>URL<input type="url" value={fonte.url} onChange={(e) => alterarFonte(indice, 'url', e.target.value)} /></label>
          <label>Acesso<input type="date" value={fonte.acessada_em} onChange={(e) => alterarFonte(indice, 'acessada_em', e.target.value)} /></label>
          <div className="admin-draft-source__actions"><button type="button" onClick={() => moverFonte(indice, -1)} disabled={!indice} aria-label={`Mover referência ${indice + 1} para cima`}>↑</button><button type="button" onClick={() => moverFonte(indice, 1)} disabled={indice === formulario.referencias.length - 1} aria-label={`Mover referência ${indice + 1} para baixo`}>↓</button><button type="button" onClick={() => atualizar('referencias', formulario.referencias.filter((_, atual) => atual !== indice))} disabled={formulario.referencias.length === 1}>Remover</button></div>
        </div>)}
        {erros.referencias && <p className="admin-field-error" role="alert">{erros.referencias}</p>}
        <button type="button" className="button-secondary" onClick={() => atualizar('referencias', [...formulario.referencias, { ...VAZIA }])}>Adicionar referência</button>
      </fieldset>
      </fieldset>
      <div className="admin-draft-editor__actions"><button type="button" className="button-secondary" onClick={cancelar}>{somenteLeitura ? 'Fechar' : 'Cancelar'}</button>{!somenteLeitura && <button type="submit" disabled={salvando || !alterado}>{salvando ? 'Salvando…' : 'Salvar alterações'}</button>}</div>
    </form>
  )
}

function RelatorioValidacao({ resultado, revisaoAtual, filtro, aoFiltrar, aoFechar, aoAbrirPergunta }) {
  const desatualizado = resultado.revisao_validada !== revisaoAtual
  const itens = resultado.achados.filter((item) => !filtro || item.nivel === filtro)
  return <section className="admin-draft-validation" aria-labelledby="draft-validation-title">
    <div className="admin-section-heading"><div><span className="admin-draft-badge">VALIDAÇÃO AUTOMÁTICA</span><h4 id="draft-validation-title">Relatório da revisão {resultado.revisao_validada}</h4></div><button type="button" className="button-secondary" onClick={aoFechar}>Fechar relatório</button></div>
    {desatualizado && <p className="admin-warning" role="alert">Este relatório está desatualizado. O rascunho agora está na revisão {revisaoAtual}; execute uma nova validação.</p>}
    <p className="admin-note">A validação verifica estrutura e coerência editorial básica. Ela não confirma a exatidão factual das respostas nem acessa os links informados.</p>
    <dl className="admin-validation-summary">
      <div><dt>Examinadas</dt><dd>{resultado.resumo.perguntas_examinadas}</dd></div><div><dt>Publicáveis</dt><dd>{resultado.resumo.perguntas_publicaveis}</dd></div>
      <div className="is-error"><dt>Erros</dt><dd>{resultado.resumo.erros}</dd></div><div className="is-warning"><dt>Avisos</dt><dd>{resultado.resumo.avisos}</dd></div><div><dt>Informações</dt><dd>{resultado.resumo.informacoes}</dd></div>
    </dl>
    <div className="admin-validation-filters" role="group" aria-label="Filtrar achados por severidade">
      <button type="button" className={!filtro ? 'is-active' : 'button-secondary'} onClick={() => aoFiltrar('')}>Todos</button>
      {Object.entries(ROTULOS_NIVEL).map(([nivel, rotulo]) => <button type="button" key={nivel} className={filtro === nivel ? 'is-active' : 'button-secondary'} onClick={() => aoFiltrar(nivel)}>{rotulo}</button>)}
    </div>
    {!itens.length ? <p className="admin-empty">Nenhum achado para o filtro selecionado.</p> : <ol className="admin-validation-findings">{itens.map((item, indice) => <li key={`${item.codigo}-${item.pergunta_id || 'catalogo'}-${indice}`} className={`is-${item.nivel.toLowerCase()}`}>
      <div><span className="admin-validation-level">{item.nivel}</span><code>{item.codigo}</code></div><strong>{item.id_editorial || 'Catálogo'}</strong>{item.campo && <span>Campo: {item.campo}</span>}
      <p>{item.mensagem}</p>{item.recomendacao && <small>{item.recomendacao}</small>}{item.pergunta_id && <button type="button" className="button-secondary" onClick={() => aoAbrirPergunta(item.pergunta_id)}>Abrir pergunta</button>}
    </li>)}</ol>}
  </section>
}

export default function AdminRascunhos({ catalogos, aoExpirarSessao, aoAlterarFormulario }) {
  const [rascunhos, setRascunhos] = useState([])
  const [selecionado, setSelecionado] = useState(null)
  const [perguntas, setPerguntas] = useState(null)
  const [categoriasRascunho, setCategoriasRascunho] = useState([])
  const [editor, setEditor] = useState(null)
  const [historico, setHistorico] = useState(null)
  const [busca, setBusca] = useState('')
  const [tipo, setTipo] = useState('')
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [formularioSujo, setFormularioSujo] = useState(false)
  const [validacao, setValidacao] = useState(null)
  const [validando, setValidando] = useState(false)
  const [filtroValidacao, setFiltroValidacao] = useState('')

  useEffect(() => {
    aoAlterarFormulario?.(formularioSujo)
    return () => aoAlterarFormulario?.(false)
  }, [aoAlterarFormulario, formularioSujo])

  const podeAbandonarFormulario = () => !formularioSujo || window.confirm('Descartar as alterações não salvas?')

  const tratarErro = useCallback((error) => {
    if (error.status === 401) aoExpirarSessao()
    else setErro(erroOperacao(error))
  }, [aoExpirarSessao])
  const carregar = useCallback(async () => {
    setCarregando(true); setErro('')
    try {
      const dados = await listarRascunhosOficiais({ limite: 100 })
      setRascunhos(dados.itens)
    } catch (error) { tratarErro(error) } finally { setCarregando(false) }
  }, [tratarErro])
  useEffect(() => {
    let ativo = true
    listarRascunhosOficiais({ limite: 100 }).then((dados) => {
      if (!ativo) return
      setRascunhos(dados.itens); setCarregando(false)
    }).catch((error) => {
      if (!ativo) return
      tratarErro(error); setCarregando(false)
    })
    return () => { ativo = false }
  }, [tratarErro])

  const abrir = async (rascunho) => {
    setErro(''); setEditor(null); setHistorico(null); setValidacao(null)
    try {
      const [atual, lista, categorias] = await Promise.all([
        obterRascunhoOficial(rascunho.id), listarPerguntasRascunho(rascunho.id, { limite: 20 }), listarCategoriasRascunho(rascunho.id),
      ])
      setSelecionado(atual); setPerguntas(lista); setCategoriasRascunho(categorias)
    } catch (error) { tratarErro(error) }
  }
  const atualizarPerguntas = async (rascunho = selecionado) => {
    const [atual, lista, categorias] = await Promise.all([
      obterRascunhoOficial(rascunho.id),
      listarPerguntasRascunho(rascunho.id, { limite: 20, busca, tipo_alteracao: tipo }),
      listarCategoriasRascunho(rascunho.id),
    ])
    setSelecionado(atual); setPerguntas(lista); setCategoriasRascunho(categorias)
  }
  const criar = async (catalogo) => {
    const nome = window.prompt(`Nome do rascunho baseado em ${catalogo.catalogo_id}:`)
    if (!nome?.trim() || !window.confirm('Criar este rascunho com uma cópia integral do catálogo publicado?')) return
    try { const novo = await criarRascunhoOficial(catalogo.id, nome.trim()); setSucesso('Rascunho criado com sucesso.'); await carregar(); await abrir(novo) } catch (error) { tratarErro(error) }
  }
  const editar = async (item) => {
    try { setEditor(await obterPerguntaRascunho(selecionado.id, item.id)) } catch (error) { tratarErro(error) }
  }
  const salvar = async (dados, perguntaId) => {
    try {
      await salvarPerguntaRascunho(selecionado.id, perguntaId, dados, selecionado.revisao)
      setFormularioSujo(false); setEditor(null); setSucesso('Pergunta salva no rascunho.'); await atualizarPerguntas()
    } catch (error) {
      if (error.status === 412) {
        const atual = await obterRascunhoOficial(selecionado.id)
        setSelecionado(atual)
      }
      throw error
    }
  }
  const alterarRemocao = async (item, restaurar) => {
    const acao = restaurar ? 'restaurar' : 'marcar como removida'
    if (!window.confirm(`Deseja ${acao} a pergunta ${item.id_editorial}?`)) return
    try {
      const resposta = restaurar
        ? await restaurarPerguntaRascunho(selecionado.id, item.id, selecionado.revisao)
        : await removerPerguntaRascunho(selecionado.id, item.id, selecionado.revisao)
      setSelecionado((atual) => ({ ...atual, revisao: resposta.revisao_rascunho }))
      setSucesso(restaurar ? 'Pergunta restaurada.' : 'Pergunta marcada como removida.')
      await atualizarPerguntas({ ...selecionado, revisao: resposta.revisao_rascunho })
    } catch (error) { tratarErro(error) }
  }
  const consultarHistorico = async () => {
    if (!podeAbandonarFormulario()) return
    try { setHistorico(await listarHistoricoRascunho(selecionado.id)); setEditor(null) } catch (error) { tratarErro(error) }
  }
  const executarValidacao = async () => {
    if (!podeAbandonarFormulario()) return
    setValidando(true); setErro(''); setFiltroValidacao('')
    try { setValidacao(await validarRascunhoOficial(selecionado.id)); setEditor(null); setHistorico(null) }
    catch (error) { tratarErro(error) } finally { setValidando(false) }
  }
  const abrirPerguntaDoRelatorio = async (perguntaId) => {
    try { setEditor(await obterPerguntaRascunho(selecionado.id, perguntaId)); setValidacao(null) }
    catch (error) { tratarErro(error) }
  }
  const descartar = async () => {
    const motivo = window.prompt('Informe o motivo do descarte:')
    if (!motivo?.trim() || !window.confirm('Descartar o rascunho? Ele continuará disponível somente para consulta.')) return
    try { const atual = await descartarRascunhoOficial(selecionado.id, motivo.trim(), selecionado.revisao); setSelecionado(atual); setSucesso('Rascunho descartado e bloqueado para edição.'); await carregar() } catch (error) { tratarErro(error) }
  }
  const categorias = useMemo(() => categoriasRascunho.map((item) => ({ ...item, id: item.categoria_id })), [categoriasRascunho])

  if (selecionado) return (
    <section className="admin-draft-workspace" aria-labelledby="admin-draft-title">
      <header className="admin-draft-header"><div><span className="admin-draft-badge">RASCUNHO — NÃO PUBLICADO</span><h3 id="admin-draft-title">{selecionado.nome}</h3><p>{rotuloModo(selecionado.modo)} · origem {selecionado.catalogo_id} v{selecionado.versao_base}</p></div><dl><div><dt>Estado</dt><dd>{selecionado.status}</dd></div><div><dt>Revisão</dt><dd>{selecionado.revisao}</dd></div><div><dt>Salvamento</dt><dd>{editor ? 'Edição aberta' : 'Sincronizado'}</dd></div></dl></header>
      <div className="admin-draft-toolbar"><button type="button" className="button-secondary" onClick={() => { if (podeAbandonarFormulario()) { setFormularioSujo(false); setSelecionado(null); setEditor(null); setValidacao(null) } }}>Voltar aos rascunhos</button><button type="button" onClick={() => { if (podeAbandonarFormulario()) { setValidacao(null); setEditor(criarFormulario(selecionado.modo, null, categorias[0]?.id)) } }} disabled={selecionado.status !== 'EM_EDICAO'}>Adicionar pergunta</button><button type="button" className="button-secondary" onClick={consultarHistorico}>Histórico editorial</button><button type="button" onClick={executarValidacao} disabled={validando}>{validando ? 'Validando…' : 'Validar rascunho'}</button>{selecionado.status === 'EM_EDICAO' && <button type="button" className="button-danger" onClick={descartar}>Descartar rascunho</button>}</div>
      {erro && <p className="admin-error" role="alert">{erro}</p>}{sucesso && <p className="admin-success" role="status">{sucesso}</p>}
      {!editor && !historico && !validacao && <GestaoCategorias rascunho={selecionado} categorias={categoriasRascunho} aoAtualizar={() => atualizarPerguntas()} aoErro={tratarErro} />}
      {!editor && !historico && !validacao && <AdminRevisaoRascunho rascunho={selecionado} aoSincronizar={async () => { await atualizarPerguntas(); await carregar() }} aoExpirarSessao={aoExpirarSessao} aoAlterarFormulario={setFormularioSujo} />}
      {editor && <EditorPergunta key={editor.id || 'nova'} rascunho={selecionado} pergunta={editor.id ? editor : null} categorias={categorias} aoCancelar={() => setEditor(null)} aoSalvar={salvar} aoAlterarSujo={setFormularioSujo} somenteLeitura={selecionado.status !== 'EM_EDICAO' || editor.tipo_alteracao === 'REMOVIDA'} />}
      {validacao && <RelatorioValidacao resultado={validacao} revisaoAtual={selecionado.revisao} filtro={filtroValidacao} aoFiltrar={setFiltroValidacao} aoFechar={() => setValidacao(null)} aoAbrirPergunta={abrirPerguntaDoRelatorio} />}
      {historico && <section className="admin-draft-history"><div className="admin-section-heading"><h4>Histórico editorial</h4><button type="button" className="button-secondary" onClick={() => setHistorico(null)}>Fechar histórico</button></div>{!historico.itens.length ? <p className="admin-empty">Nenhuma alteração registrada.</p> : <ol>{historico.itens.map((item) => <li key={item.id}><strong>{item.tipo}</strong><span>Revisão {item.revisao_anterior ?? 'inicial'} → {item.revisao_nova}</span><small>{formatarData(item.ocorrida_em)} · {item.id_editorial || 'Catálogo'}</small></li>)}</ol>}</section>}
      {!editor && !historico && !validacao && <><form className="admin-draft-filters" onSubmit={(e) => { e.preventDefault(); atualizarPerguntas() }} aria-label="Filtros das perguntas do rascunho"><label>Pesquisar<input value={busca} onChange={(e) => setBusca(e.target.value)} /></label><label>Alteração<select value={tipo} onChange={(e) => setTipo(e.target.value)}><option value="">Todas</option><option value="INALTERADA">Inalteradas</option><option value="MODIFICADA">Modificadas</option><option value="ADICIONADA">Adicionadas</option><option value="REMOVIDA">Removidas</option></select></label><button type="submit">Aplicar filtros</button></form>
        {!perguntas?.itens.length ? <p className="admin-empty">Nenhuma pergunta corresponde aos filtros.</p> : <div className="admin-draft-question-list">{perguntas.itens.map((item) => <article key={item.id} className={`admin-draft-question ${item.tipo_alteracao === 'REMOVIDA' ? 'is-removed' : ''}`}><div><span>{item.id_editorial}</span><span className="admin-status">{item.tipo_alteracao}</span></div><h4>{item.enunciado}</h4><p>{item.categoria_nome} · revisão {item.revisao}</p><div><button type="button" onClick={() => editar(item)}>{selecionado.status === 'EM_EDICAO' && item.tipo_alteracao !== 'REMOVIDA' ? 'Editar' : 'Visualizar'}</button>{item.tipo_alteracao === 'REMOVIDA' ? <button type="button" className="button-secondary" onClick={() => alterarRemocao(item, true)} disabled={selecionado.status !== 'EM_EDICAO'}>Restaurar</button> : <button type="button" className="button-danger" onClick={() => alterarRemocao(item, false)} disabled={selecionado.status !== 'EM_EDICAO'}>Remover</button>}</div></article>)}</div>}</>}
    </section>
  )

  return (
    <section className="admin-drafts" aria-labelledby="admin-drafts-title"><div className="admin-section-heading"><div><span className="admin-draft-badge">RASCUNHOS — NÃO PUBLICADOS</span><h3 id="admin-drafts-title">Edição versionada</h3></div><button type="button" className="button-secondary" onClick={carregar}>Atualizar rascunhos</button></div>
      {erro && <p className="admin-error" role="alert">{erro}</p>}{sucesso && <p className="admin-success" role="status">{sucesso}</p>}
      {carregando ? <p className="admin-loading" role="status">Carregando rascunhos…</p> : !rascunhos.length ? <p className="admin-empty">Nenhum rascunho criado.</p> : <div className="admin-draft-list">{rascunhos.map((item) => <article key={item.id}><div><span className="admin-card-kicker">{rotuloModo(item.modo)}</span><span className="admin-status">{item.status}</span></div><h4>{item.nome}</h4><p>{item.catalogo_id} v{item.versao_base} · revisão {item.revisao}</p><p>{item.adicionadas} adicionadas · {item.modificadas} modificadas · {item.removidas} removidas</p><small>Criador: {item.criado_por_id || 'não informado'} · atualizado em {formatarData(item.atualizado_em)}</small><button type="button" onClick={() => abrir(item)}>{item.status === 'EM_EDICAO' ? 'Gerenciar rascunho' : 'Consultar rascunho'}</button></article>)}</div>}
      <div className="admin-draft-create"><h4>Criar a partir da versão ativa</h4>{catalogos.filter((catalogo) => catalogo.status_registro === 'ATIVO').map((catalogo) => <button key={catalogo.id} type="button" className="button-secondary" onClick={() => criar(catalogo)}>Criar rascunho de {rotuloModo(catalogo.modo)} · {catalogo.catalogo_id} v{catalogo.versao} ({catalogo.quantidade_perguntas} perguntas)</button>)}</div>
      <ImportacaoJson catalogos={catalogos} aoConcluir={carregar} aoErro={tratarErro} />
    </section>
  )
}
