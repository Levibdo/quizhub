import { useCallback, useEffect, useRef, useState } from 'react'
import {
  criarPerguntaMeuConteudo,
  editarPerguntaMeuConteudo,
  excluirPerguntaMeuConteudo,
  listarPerguntasMeuConteudo,
} from '../../services/api'

const LIMITE_PAGINA = 20
const MAX_BIGINT = '9223372036854775807'

function normalizarInteiro(valor) {
  if (!/^\d+$/.test(valor)) return null
  const normalizado = valor.replace(/^0+(?=\d)/, '')
  if (normalizado.length > MAX_BIGINT.length ||
      (normalizado.length === MAX_BIGINT.length && normalizado > MAX_BIGINT)) return null
  return normalizado
}

function erroObrigatorio(campos) {
  const erros = {}
  for (const [campo, valor] of Object.entries(campos)) {
    if (!String(valor ?? '').trim()) erros[campo] = 'Campo obrigatório.'
  }
  return erros
}

function Campo({ id, label, erro, children }) {
  return <div className="question-field"><label htmlFor={id}>{label}</label>{children}{erro && <span role="alert">{erro}</span>}</div>
}

function FormularioClassico({ categorias, pergunta, enviando, aoSalvar, aoCancelar }) {
  const [dados, setDados] = useState(() => ({
    categoria_id: pergunta?.categoria_id ?? categorias[0]?.id ?? '',
    enunciado: pergunta?.enunciado ?? '', alternativa_a: pergunta?.alternativa_a ?? '',
    alternativa_b: pergunta?.alternativa_b ?? '', alternativa_c: pergunta?.alternativa_c ?? '',
    alternativa_d: pergunta?.alternativa_d ?? '', alternativa_correta: pergunta?.alternativa_correta ?? 'A',
    explicacao: pergunta?.explicacao ?? '',
  }))
  const [erros, setErros] = useState({})
  const definir = (campo, valor) => setDados((atual) => ({ ...atual, [campo]: valor }))

  function enviar(evento) {
    evento.preventDefault()
    const obrigatorios = erroObrigatorio(dados)
    if (!['A', 'B', 'C', 'D'].includes(dados.alternativa_correta)) obrigatorios.alternativa_correta = 'Selecione A, B, C ou D.'
    setErros(obrigatorios)
    if (Object.keys(obrigatorios).length) return
    const normalizados = Object.fromEntries(Object.entries(dados).map(([chave, valor]) => [chave, typeof valor === 'string' ? valor.trim() : valor]))
    aoSalvar(normalizados)
  }

  return (
    <form className="question-form" aria-label={pergunta ? 'Editar pergunta clássica' : 'Nova pergunta clássica'} onSubmit={enviar}>
      <h3>{pergunta ? 'Editar pergunta' : 'Nova pergunta do Quiz Clássico'}</h3>
      <Campo id="question-category" label="Categoria" erro={erros.categoria_id}><select id="question-category" value={dados.categoria_id} disabled={enviando} onChange={(e) => definir('categoria_id', e.target.value)}>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}{c.ativa ? '' : ' (inativa)'}</option>)}</select></Campo>
      <Campo id="question-statement" label="Enunciado" erro={erros.enunciado}><textarea id="question-statement" rows={3} value={dados.enunciado} disabled={enviando} onChange={(e) => definir('enunciado', e.target.value)} /></Campo>
      <div className="question-form__alternatives">
        {['a', 'b', 'c', 'd'].map((letra) => <Campo key={letra} id={`question-alternative-${letra}`} label={`Alternativa ${letra.toUpperCase()}`} erro={erros[`alternativa_${letra}`]}><input id={`question-alternative-${letra}`} value={dados[`alternativa_${letra}`]} disabled={enviando} onChange={(e) => definir(`alternativa_${letra}`, e.target.value)} /></Campo>)}
      </div>
      <Campo id="question-correct" label="Alternativa correta" erro={erros.alternativa_correta}><select id="question-correct" value={dados.alternativa_correta} disabled={enviando} onChange={(e) => definir('alternativa_correta', e.target.value)}>{['A', 'B', 'C', 'D'].map((letra) => <option key={letra}>{letra}</option>)}</select></Campo>
      <Campo id="question-explanation" label="Explicação" erro={erros.explicacao}><textarea id="question-explanation" rows={3} value={dados.explicacao} disabled={enviando} onChange={(e) => definir('explicacao', e.target.value)} /></Campo>
      <div className="question-form__actions"><button disabled={enviando}>{enviando ? 'Salvando...' : 'Salvar pergunta'}</button><button type="button" className="button-ghost" disabled={enviando} onClick={aoCancelar}>Cancelar</button></div>
    </form>
  )
}

function FormularioNemPato({ categorias, pergunta, enviando, aoSalvar, aoCancelar }) {
  const [dados, setDados] = useState(() => ({
    categoria_id: pergunta?.categoria_id ?? categorias[0]?.id ?? '', enunciado: pergunta?.enunciado ?? '',
    resposta_numerica: pergunta?.resposta_numerica ?? '', unidade: pergunta?.unidade ?? '',
    explicacao: pergunta?.explicacao ?? '', fonte: pergunta?.fonte ?? '',
  }))
  const [erros, setErros] = useState({})
  const definir = (campo, valor) => setDados((atual) => ({ ...atual, [campo]: valor }))

  function enviar(evento) {
    evento.preventDefault()
    const obrigatorios = erroObrigatorio({ categoria_id: dados.categoria_id, enunciado: dados.enunciado, resposta_numerica: dados.resposta_numerica, explicacao: dados.explicacao })
    const numero = normalizarInteiro(String(dados.resposta_numerica).trim())
    if (String(dados.resposta_numerica).trim() && numero === null) obrigatorios.resposta_numerica = `Informe um inteiro entre 0 e ${MAX_BIGINT}.`
    setErros(obrigatorios)
    if (Object.keys(obrigatorios).length) return
    aoSalvar({
      categoria_id: dados.categoria_id, enunciado: dados.enunciado.trim(), resposta_numerica: numero,
      unidade: dados.unidade.trim() || null, explicacao: dados.explicacao.trim(), fonte: dados.fonte.trim() || null,
    })
  }

  return (
    <form className="question-form" aria-label={pergunta ? 'Editar pergunta Nem a Pato' : 'Nova pergunta Nem a Pato'} onSubmit={enviar}>
      <h3>{pergunta ? 'Editar pergunta' : 'Nova pergunta do Nem a Pato'}</h3>
      <Campo id="question-category" label="Categoria" erro={erros.categoria_id}><select id="question-category" value={dados.categoria_id} disabled={enviando} onChange={(e) => definir('categoria_id', e.target.value)}>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}{c.ativa ? '' : ' (inativa)'}</option>)}</select></Campo>
      <Campo id="question-statement" label="Enunciado" erro={erros.enunciado}><textarea id="question-statement" rows={3} value={dados.enunciado} disabled={enviando} onChange={(e) => definir('enunciado', e.target.value)} /></Campo>
      <div className="question-form__split"><Campo id="question-number" label="Resposta numérica" erro={erros.resposta_numerica}><input id="question-number" inputMode="numeric" value={dados.resposta_numerica} disabled={enviando} onChange={(e) => definir('resposta_numerica', e.target.value)} /></Campo><Campo id="question-unit" label="Unidade (opcional)"><input id="question-unit" value={dados.unidade} disabled={enviando} onChange={(e) => definir('unidade', e.target.value)} /></Campo></div>
      <Campo id="question-explanation" label="Explicação" erro={erros.explicacao}><textarea id="question-explanation" rows={3} value={dados.explicacao} disabled={enviando} onChange={(e) => definir('explicacao', e.target.value)} /></Campo>
      <Campo id="question-source" label="Fonte (opcional)"><input id="question-source" value={dados.fonte} disabled={enviando} onChange={(e) => definir('fonte', e.target.value)} /></Campo>
      <div className="question-form__actions"><button disabled={enviando}>{enviando ? 'Salvando...' : 'Salvar pergunta'}</button><button type="button" className="button-ghost" disabled={enviando} onClick={aoCancelar}>Cancelar</button></div>
    </form>
  )
}

function ModalExcluirPergunta({ pergunta, enviando, aoCancelar, aoConfirmar }) {
  const cancelarRef = useRef(null)
  useEffect(() => {
    cancelarRef.current?.focus()
    const fechar = (evento) => { if (evento.key === 'Escape' && !enviando) aoCancelar() }
    window.addEventListener?.('keydown', fechar)
    return () => window.removeEventListener?.('keydown', fechar)
  }, [aoCancelar, enviando])
  return <div className="content-dialog-backdrop" role="presentation"><section className="content-dialog" role="dialog" aria-modal="true" aria-labelledby="question-delete-title"><span className="content-eyebrow">Confirmação</span><h3 id="question-delete-title">Excluir esta pergunta?</h3><p>{pergunta.enunciado}</p><p>A pergunta não poderá ser restaurada nesta interface. Partidas anteriores permanecem preservadas.</p><div className="content-dialog__actions"><button className="content-danger" disabled={enviando} onClick={aoConfirmar}>{enviando ? 'Excluindo...' : 'Excluir pergunta'}</button><button ref={cancelarRef} className="button-secondary" disabled={enviando} onClick={aoCancelar}>Cancelar</button></div></section></div>
}

export default function PainelPerguntas({ modo, categorias, uso, aoAtualizarResumo, aoExpirarSessao }) {
  const [perguntas, setPerguntas] = useState([])
  const [categoriaFiltro, setCategoriaFiltro] = useState('')
  const [ativaFiltro, setAtivaFiltro] = useState('')
  const [temMais, setTemMais] = useState(false)
  const [carregando, setCarregando] = useState(true)
  const [carregandoMais, setCarregandoMais] = useState(false)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [formulario, setFormulario] = useState(null)
  const [exclusao, setExclusao] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const enviandoRef = useRef(false)
  const requisicaoRef = useRef(0)
  const perguntasRef = useRef([])
  const retornoFocoRef = useRef(null)

  const fecharExclusao = useCallback(() => {
    setExclusao(null)
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => retornoFocoRef.current?.focus())
    else retornoFocoRef.current?.focus?.()
  }, [])

  const carregar = useCallback(async ({ acumular = false } = {}) => {
    const requisicao = ++requisicaoRef.current
    if (acumular) setCarregandoMais(true); else setCarregando(true)
    setErro('')
    try {
      const pagina = await listarPerguntasMeuConteudo(modo, {
        categoria_id: categoriaFiltro || undefined,
        ativa: ativaFiltro === '' ? '' : ativaFiltro === 'true',
        offset: acumular ? perguntasRef.current.length : 0, limit: LIMITE_PAGINA,
      })
      if (requisicao !== requisicaoRef.current) return
      const proximas = acumular ? [...perguntasRef.current, ...pagina] : pagina
      perguntasRef.current = proximas
      setPerguntas(proximas)
      setTemMais(pagina.length === LIMITE_PAGINA)
    } catch (error) {
      if (requisicao !== requisicaoRef.current) return
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.message)
    } finally {
      if (requisicao === requisicaoRef.current) { setCarregando(false); setCarregandoMais(false) }
    }
  }, [ativaFiltro, aoExpirarSessao, categoriaFiltro, modo])

  useEffect(() => {
    const inicio = window.setTimeout(() => carregar(), 0)
    return () => { window.clearTimeout(inicio); requisicaoRef.current += 1 }
  }, [carregar])

  const categoriasAtivas = categorias.filter((categoria) => categoria.ativa && !categoria.excluida_em)
  const categoriasFormulario = formulario?.id && !categoriasAtivas.some((categoria) => categoria.id === formulario.categoria_id)
    ? [...categoriasAtivas, categorias.find((categoria) => categoria.id === formulario.categoria_id)].filter(Boolean)
    : categoriasAtivas

  async function executarMutacao(acao, mensagem) {
    if (enviandoRef.current) return
    enviandoRef.current = true; setEnviando(true); setErro('')
    try {
      await acao(); setFormulario(null); setExclusao(null); setSucesso(mensagem)
      await Promise.all([carregar(), aoAtualizarResumo()])
    } catch (error) {
      if (error.status === 401) aoExpirarSessao()
      else setErro(error.status === 409 ? error.message : `Não foi possível concluir a operação. ${error.message}`)
    } finally { enviandoRef.current = false; setEnviando(false) }
  }

  function salvar(dados) {
    if (!formulario?.id) return executarMutacao(() => criarPerguntaMeuConteudo(modo, dados), 'Pergunta criada.')
    const alteracoes = Object.fromEntries(Object.entries(dados).filter(([campo, valor]) => {
      const anterior = formulario[campo] ?? null
      return String(valor ?? '') !== String(anterior ?? '')
    }))
    if (!Object.keys(alteracoes).length) { setFormulario(null); return undefined }
    return executarMutacao(() => editarPerguntaMeuConteudo(modo, formulario.id, alteracoes), 'Pergunta atualizada.')
  }

  const Formulario = modo === 'QUIZ_CLASSICO' ? FormularioClassico : FormularioNemPato
  return <section className="questions-panel" aria-labelledby="questions-title">
    <div className="content-section-heading"><div><span className="content-eyebrow">Perguntas próprias</span><h2 id="questions-title">Perguntas</h2></div><button disabled={enviando || uso?.perguntas.usadas >= uso?.perguntas.limite || !categoriasAtivas.length} onClick={() => { setFormulario({}); setSucesso(''); setErro('') }}>Nova pergunta</button></div>
    {!categoriasAtivas.length && <p className="content-state" role="status">Crie e ative uma categoria deste modo antes de cadastrar perguntas.</p>}
    <div className="question-filters"><label htmlFor="question-filter-category">Categoria</label><select id="question-filter-category" value={categoriaFiltro} onChange={(e) => { requisicaoRef.current += 1; setCategoriaFiltro(e.target.value) }}><option value="">Todas</option>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select><label htmlFor="question-filter-active">Estado</label><select id="question-filter-active" value={ativaFiltro} onChange={(e) => { requisicaoRef.current += 1; setAtivaFiltro(e.target.value) }}><option value="">Todos</option><option value="true">Ativas</option><option value="false">Inativas</option></select></div>
    {sucesso && <p className="content-message" role="status">{sucesso}</p>}{erro && <p className="mensagem-erro" role="alert">{erro}</p>}
    {formulario && <Formulario key={formulario.id ?? `nova-${modo}`} categorias={categoriasFormulario} pergunta={formulario.id ? formulario : null} enviando={enviando} aoSalvar={salvar} aoCancelar={() => setFormulario(null)} />}
    {carregando ? <p className="content-state" role="status">Carregando perguntas...</p> : perguntas.length === 0 ? <div className="content-empty"><strong>Nenhuma pergunta encontrada.</strong><p>Ajuste os filtros ou crie a primeira pergunta.</p></div> : <ul className="question-list">{perguntas.map((pergunta) => <li key={pergunta.id} className="question-list__item"><div><span className={pergunta.ativa ? 'content-badge content-badge--active' : 'content-badge'}>{pergunta.ativa ? 'Ativa' : 'Inativa'}</span><h3>{pergunta.enunciado}</h3><p>{categorias.find((c) => c.id === pergunta.categoria_id)?.nome ?? 'Categoria indisponível'}</p></div><div className="content-category-card__actions"><button className="button-secondary" disabled={enviando} onClick={() => { setFormulario(pergunta); setSucesso(''); setErro('') }}>Editar</button><button className="button-secondary" disabled={enviando} onClick={() => executarMutacao(() => editarPerguntaMeuConteudo(modo, pergunta.id, { ativa: !pergunta.ativa }), pergunta.ativa ? 'Pergunta desativada.' : 'Pergunta ativada.')}>{pergunta.ativa ? 'Desativar' : 'Ativar'}</button><button className="button-ghost" disabled={enviando} onClick={(evento) => { retornoFocoRef.current = evento.currentTarget; setExclusao(pergunta) }}>Excluir</button></div></li>)}</ul>}
    {temMais && !carregando && <button className="button-secondary question-load-more" disabled={carregandoMais} onClick={() => carregar({ acumular: true })}>{carregandoMais ? 'Carregando...' : 'Carregar mais'}</button>}
    {exclusao && <ModalExcluirPergunta pergunta={exclusao} enviando={enviando} aoCancelar={fecharExclusao} aoConfirmar={() => executarMutacao(() => excluirPerguntaMeuConteudo(modo, exclusao.id), 'Pergunta excluída.')} />}
  </section>
}
