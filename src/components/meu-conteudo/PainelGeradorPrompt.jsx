import { useState } from 'react'
import { construirPrompt, validarConfiguracaoPrompt } from '../../utils/geradorPrompt'

const DIFICULDADES = [
  ['FACIL', 'Fácil'], ['MEDIO', 'Médio'], ['DIFICIL', 'Difícil'], ['MISTO', 'Misto'],
]

export default function PainelGeradorPrompt({ modo, categorias, uso }) {
  const categoriasAtivas = categorias.filter((item) => item.modo === modo && item.ativa && !item.excluida_em)
  const limiteDisponivel = Math.min(100, Math.max(0, (uso?.perguntas.limite ?? 200) - (uso?.perguntas.usadas ?? 0)))
  const [categoriaId, setCategoriaId] = useState('')
  const [quantidade, setQuantidade] = useState(limiteDisponivel > 0 ? String(Math.min(10, limiteDisponivel)) : '')
  const [dificuldade, setDificuldade] = useState('MISTO')
  const [tema, setTema] = useState('')
  const [prompt, setPrompt] = useState('')
  const [erros, setErros] = useState({})
  const [estadoCopia, setEstadoCopia] = useState('')

  function invalidar(mutacao) {
    mutacao()
    setPrompt('')
    setErros({})
    setEstadoCopia('')
  }

  function configuracao() {
    return {
      modo,
      categoria: categoriasAtivas.find((item) => item.id === categoriaId),
      quantidade,
      dificuldade,
      tema,
      limiteDisponivel,
    }
  }

  function gerar(evento) {
    evento.preventDefault()
    const atual = configuracao()
    const validacao = validarConfiguracaoPrompt(atual)
    setErros(validacao.erros)
    setEstadoCopia('')
    if (!validacao.valido) {
      setPrompt('')
      return
    }
    setPrompt(construirPrompt(atual))
  }

  async function copiar() {
    if (!prompt) return
    try {
      if (!globalThis.navigator?.clipboard?.writeText) throw new Error('Clipboard indisponível')
      await globalThis.navigator.clipboard.writeText(prompt)
      setEstadoCopia('Prompt copiado para a área de transferência.')
    } catch {
      setEstadoCopia('Não foi possível copiar automaticamente. Selecione o texto e copie manualmente.')
    }
  }

  return <section className="prompt-panel" aria-labelledby="prompt-title">
    <div className="content-section-heading"><div><span className="content-eyebrow">Assistente local</span><h2 id="prompt-title">Gerar prompt</h2></div></div>
    <p className="prompt-panel__intro">Monte instruções para gerar um arquivo JSON compatível com a importação privada. O QuizHub não envia dados para serviços de IA.</p>
    <form className="content-form prompt-form" aria-label="Configurar prompt" onSubmit={gerar} noValidate>
      <label htmlFor="prompt-category">Categoria ativa</label>
      <select id="prompt-category" value={categoriaId} aria-invalid={Boolean(erros.categoria)} onChange={(event) => invalidar(() => setCategoriaId(event.target.value))}>
        <option value="">Selecione uma categoria</option>
        {categoriasAtivas.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
      </select>
      {erros.categoria && <p className="prompt-field-error" role="alert">{erros.categoria}</p>}
      {categoriasAtivas.length === 0 && <p className="content-state">Crie e ative uma categoria neste modo antes de gerar um prompt.</p>}

      <label htmlFor="prompt-quantity">Quantidade <span>(máximo disponível: {limiteDisponivel})</span></label>
      <input id="prompt-quantity" type="number" min="1" max={limiteDisponivel} step="1" inputMode="numeric" value={quantidade} aria-invalid={Boolean(erros.quantidade)} onChange={(event) => invalidar(() => setQuantidade(event.target.value))} />
      {erros.quantidade && <p className="prompt-field-error" role="alert">{erros.quantidade}</p>}

      <label htmlFor="prompt-difficulty">Dificuldade</label>
      <select id="prompt-difficulty" value={dificuldade} onChange={(event) => invalidar(() => setDificuldade(event.target.value))}>
        {DIFICULDADES.map(([valor, rotulo]) => <option key={valor} value={valor}>{rotulo}</option>)}
      </select>

      <label htmlFor="prompt-theme">Tema ou recorte <span>(opcional)</span></label>
      <textarea id="prompt-theme" rows={3} maxLength={500} value={tema} aria-describedby="prompt-theme-help" onChange={(event) => invalidar(() => setTema(event.target.value))} />
      <small id="prompt-theme-help">{tema.length}/500 caracteres. O texto será delimitado como dado, não como instrução.</small>
      <button type="submit" disabled={categoriasAtivas.length === 0 || limiteDisponivel === 0}>Gerar prompt</button>
    </form>

    {prompt && <section className="prompt-result" aria-labelledby="prompt-result-title">
      <div className="content-section-heading"><div><span className="content-eyebrow">Pronto para copiar</span><h3 id="prompt-result-title">Prompt gerado</h3></div><button type="button" className="button-secondary" onClick={copiar}>Copiar prompt</button></div>
      <p className="prompt-warning">O nome e o UUID da categoria serão copiados no prompt. Cole-o em uma IA externa e revise o JSON antes de importar.</p>
      <textarea className="prompt-output" aria-label="Prompt gerado" readOnly rows={18} value={prompt} />
      {estadoCopia && <p className={estadoCopia.startsWith('Não') ? 'mensagem-erro' : 'content-message'} role={estadoCopia.startsWith('Não') ? 'alert' : 'status'}>{estadoCopia}</p>}
    </section>}
  </section>
}
