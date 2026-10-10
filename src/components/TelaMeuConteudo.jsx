import { useCallback, useEffect, useRef, useState } from 'react'
import {
  criarCategoriaMeuConteudo,
  editarCategoriaMeuConteudo,
  excluirCategoriaMeuConteudo,
  listarCategoriasMeuConteudo,
  obterResumoMeuConteudo,
} from '../services/api'
import PainelPerguntas from './meu-conteudo/PainelPerguntas'
import PainelImportacao from './meu-conteudo/PainelImportacao'
import PainelGeradorPrompt from './meu-conteudo/PainelGeradorPrompt'

const MODOS = [
  { id: 'QUIZ_CLASSICO', nome: 'Quiz Clássico' },
  { id: 'NEM_A_PATO', nome: 'Nem a Pato' },
]

function mensagemErro(error, contexto) {
  if (error.status === 409) return error.message
  if (error.status === 422) return error.message || 'Revise os dados informados.'
  return `${contexto} ${error.message}`
}

function FormularioCategoria({ modo, categoria, ocupadas, aoSalvar, aoCancelar, enviando }) {
  const [nome, setNome] = useState(categoria?.nome ?? '')
  const [descricao, setDescricao] = useState(categoria?.descricao ?? '')
  const [erro, setErro] = useState('')

  function enviar(evento) {
    evento.preventDefault()
    const nomeNormalizado = nome.trim()
    if (!nomeNormalizado) {
      setErro('Informe o nome da categoria.')
      return
    }
    if (nomeNormalizado.length > 100) {
      setErro('O nome deve ter no máximo 100 caracteres.')
      return
    }
    setErro('')
    aoSalvar({ nome: nomeNormalizado, descricao: descricao.trim() || null })
  }

  return (
    <form className="content-form" onSubmit={enviar} aria-label={categoria ? 'Editar categoria' : 'Nova categoria'}>
      <div className="content-form__heading">
        <div>
          <span className="content-eyebrow">{categoria ? 'Edição' : 'Nova categoria'}</span>
          <h3>{categoria ? categoria.nome : `Criar em ${MODOS.find((item) => item.id === modo)?.nome}`}</h3>
        </div>
        {!categoria && <span className="content-limit">{ocupadas}/10</span>}
      </div>
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      <label htmlFor="content-category-name">Nome</label>
      <input
        id="content-category-name" value={nome} maxLength={100} required disabled={enviando}
        onChange={(event) => setNome(event.target.value)} autoFocus
      />
      <label htmlFor="content-category-description">Descrição <span>(opcional)</span></label>
      <textarea
        id="content-category-description" value={descricao} disabled={enviando} rows={3}
        onChange={(event) => setDescricao(event.target.value)}
      />
      <div className="content-form__actions">
        <button type="submit" disabled={enviando || (!categoria && ocupadas >= 10)}>
          {enviando ? 'Salvando...' : categoria ? 'Salvar alterações' : 'Criar categoria'}
        </button>
        <button type="button" className="button-ghost" disabled={enviando} onClick={aoCancelar}>Cancelar</button>
      </div>
    </form>
  )
}

function ModalExclusao({ categoria, enviando, erro, aoConfirmar, aoCancelar }) {
  const cancelarRef = useRef(null)

  useEffect(() => {
    cancelarRef.current?.focus()
    function fechar(evento) {
      if (evento.key === 'Escape' && !enviando) aoCancelar()
    }
    window.addEventListener?.('keydown', fechar)
    return () => window.removeEventListener?.('keydown', fechar)
  }, [aoCancelar, enviando])

  return (
    <div className="content-dialog-backdrop" role="presentation">
      <section className="content-dialog" role="dialog" aria-modal="true" aria-labelledby="content-delete-title" aria-describedby="content-delete-description">
        <span className="content-eyebrow">Confirmação</span>
        <h3 id="content-delete-title">Excluir “{categoria.nome}”?</h3>
        <p id="content-delete-description">A exclusão é permanente nesta interface. Perguntas existentes nessa categoria precisam ser excluídas primeiro.</p>
        {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
        <div className="content-dialog__actions">
          <button className="content-danger" type="button" disabled={enviando} onClick={aoConfirmar}>
            {enviando ? 'Excluindo...' : 'Excluir categoria'}
          </button>
          <button ref={cancelarRef} className="button-secondary" type="button" disabled={enviando} onClick={aoCancelar}>Cancelar</button>
        </div>
      </section>
    </div>
  )
}

export default function TelaMeuConteudo({ voltar, aoExpirarSessao }) {
  const [modo, setModo] = useState('QUIZ_CLASSICO')
  const [aba, setAba] = useState('categorias')
  const [versaoPerguntas, setVersaoPerguntas] = useState(0)
  const [importando, setImportando] = useState(false)
  const [resumo, setResumo] = useState(null)
  const [categorias, setCategorias] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [erroCarregamento, setErroCarregamento] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [formulario, setFormulario] = useState(null)
  const [exclusao, setExclusao] = useState(null)
  const [erroExclusao, setErroExclusao] = useState('')
  const [enviando, setEnviando] = useState(false)
  const enviandoRef = useRef(false)
  const requisicaoRef = useRef(0)
  const retornoFocoRef = useRef(null)

  function restaurarFoco() {
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => retornoFocoRef.current?.focus())
    else retornoFocoRef.current?.focus?.()
  }

  const carregar = useCallback(async (modoAtual) => {
    const requisicao = ++requisicaoRef.current
    setCarregando(true)
    setErroCarregamento('')
    try {
      const [novoResumo, novasCategorias] = await Promise.all([
        obterResumoMeuConteudo(), listarCategoriasMeuConteudo(modoAtual),
      ])
      if (requisicao !== requisicaoRef.current) return
      setResumo(novoResumo)
      setCategorias(novasCategorias)
    } catch (error) {
      if (requisicao !== requisicaoRef.current) return
      if (error.status === 401) {
        aoExpirarSessao()
        return
      }
      setErroCarregamento(mensagemErro(error, 'Não foi possível carregar seu conteúdo.'))
    } finally {
      if (requisicao === requisicaoRef.current) setCarregando(false)
    }
  }, [aoExpirarSessao])

  useEffect(() => {
    const inicio = window.setTimeout(() => carregar(modo), 0)
    return () => {
      window.clearTimeout(inicio)
      requisicaoRef.current += 1
    }
  }, [carregar, modo])

  const uso = resumo?.modos.find((item) => item.modo === modo)

  async function atualizarResumo() {
    try {
      setResumo(await obterResumoMeuConteudo())
    } catch (error) {
      if (error.status === 401) aoExpirarSessao()
      else setErro(mensagemErro(error, 'Não foi possível atualizar as quotas.'))
    }
  }

  function trocarModo(novoModo) {
    if (novoModo === modo || enviando || importando) return
    requisicaoRef.current += 1
    setModo(novoModo)
    setFormulario(null)
    setSucesso('')
  }

  async function salvarCategoria(dados) {
    if (enviandoRef.current) return
    enviandoRef.current = true
    setEnviando(true)
    setErro('')
    try {
      if (formulario?.id) await editarCategoriaMeuConteudo(formulario.id, dados)
      else await criarCategoriaMeuConteudo({ ...dados, modo })
      setSucesso(formulario?.id ? 'Categoria atualizada.' : 'Categoria criada.')
      setFormulario(null)
      await carregar(modo)
    } catch (error) {
      if (error.status === 401) aoExpirarSessao()
      else setErro(mensagemErro(error, 'Não foi possível salvar a categoria.'))
    } finally {
      enviandoRef.current = false
      setEnviando(false)
    }
  }

  async function alternarAtiva(categoria) {
    if (enviandoRef.current) return
    enviandoRef.current = true
    setEnviando(true)
    setErro('')
    try {
      await editarCategoriaMeuConteudo(categoria.id, { ativa: !categoria.ativa })
      setSucesso(categoria.ativa ? 'Categoria desativada.' : 'Categoria ativada.')
      await carregar(modo)
    } catch (error) {
      if (error.status === 401) aoExpirarSessao()
      else setErro(mensagemErro(error, 'Não foi possível alterar o estado da categoria.'))
    } finally {
      enviandoRef.current = false
      setEnviando(false)
    }
  }

  function abrirExclusao(categoria, evento) {
    retornoFocoRef.current = evento.currentTarget
    setErroExclusao('')
    setExclusao(categoria)
  }

  const fecharExclusao = useCallback(() => {
    setExclusao(null)
    setErroExclusao('')
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => retornoFocoRef.current?.focus())
    else retornoFocoRef.current?.focus?.()
  }, [])

  async function confirmarExclusao() {
    if (enviandoRef.current || !exclusao) return
    enviandoRef.current = true
    setEnviando(true)
    setErroExclusao('')
    try {
      await excluirCategoriaMeuConteudo(exclusao.id)
      setExclusao(null)
      setSucesso('Categoria excluída.')
      await carregar(modo)
      restaurarFoco()
    } catch (error) {
      if (error.status === 401) aoExpirarSessao()
      else setErroExclusao(error.status === 409
        ? 'Exclua primeiro todas as perguntas não excluídas desta categoria.'
        : mensagemErro(error, 'Não foi possível excluir a categoria.'))
    } finally {
      enviandoRef.current = false
      setEnviando(false)
    }
  }

  return (
    <section className="content-screen" aria-labelledby="content-title" aria-busy={carregando}>
      <header className="content-header">
        <div>
          <span className="content-eyebrow">Área privada</span>
          <h1 id="content-title">Meu Conteúdo</h1>
          <p>Gerencie suas categorias e perguntas para utilizar nos quizzes.</p>
        </div>
        <button className="button-ghost" type="button" disabled={importando} onClick={voltar}>Voltar ao início</button>
      </header>

      <div className="content-mode-selector" aria-label="Selecionar modo">
        {MODOS.map((item) => (
          <button key={item.id} type="button" aria-pressed={modo === item.id} disabled={enviando || importando} onClick={() => trocarModo(item.id)}>{item.nome}</button>
        ))}
      </div>

      {uso && (
        <section className="content-summary" aria-label="Uso do conteúdo">
          <div><span>Categorias</span><strong>{uso.categorias.usadas} / {uso.categorias.limite}</strong></div>
          <div><span>Perguntas</span><strong>{uso.perguntas.usadas} / {uso.perguntas.limite}</strong></div>
        </section>
      )}

      <nav className="content-tabs" aria-label="Seções de Meu Conteúdo">
        <button type="button" disabled={importando} aria-current={aba === 'categorias' ? 'page' : undefined} onClick={() => setAba('categorias')}>Categorias</button>
        <button type="button" disabled={importando} aria-current={aba === 'perguntas' ? 'page' : undefined} onClick={() => setAba('perguntas')}>Perguntas</button>
        <button type="button" disabled={importando} aria-current={aba === 'importar' ? 'page' : undefined} onClick={() => setAba('importar')}>Importar</button>
        <button type="button" disabled={importando} aria-current={aba === 'prompt' ? 'page' : undefined} onClick={() => setAba('prompt')}>Gerar prompt</button>
      </nav>

      {sucesso && <p className="content-message" role="status">{sucesso}</p>}
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      {erroCarregamento && <div className="content-state content-state--error" role="alert"><p>{erroCarregamento}</p><button type="button" onClick={() => carregar(modo)}>Tentar novamente</button></div>}
      {carregando && <div className="content-state" role="status">Carregando seu conteúdo...</div>}

      {!carregando && !erroCarregamento && aba === 'categorias' && (
        <section className="content-categories" aria-labelledby="content-categories-title">
          <div className="content-section-heading">
            <div><span className="content-eyebrow">{MODOS.find((item) => item.id === modo)?.nome}</span><h2 id="content-categories-title">Categorias</h2></div>
            {!formulario && <button type="button" disabled={enviando || uso?.categorias.usadas >= uso?.categorias.limite} onClick={() => { setFormulario({}); setSucesso('') }}>Nova categoria</button>}
          </div>

          {formulario && (
            <FormularioCategoria
              key={formulario.id ?? `nova-${modo}`} modo={modo} categoria={formulario.id ? formulario : null}
              ocupadas={uso?.categorias.usadas ?? 0} enviando={enviando} aoSalvar={salvarCategoria}
              aoCancelar={() => setFormulario(null)}
            />
          )}

          {categorias.length === 0 ? (
            <div className="content-empty"><strong>Nenhuma categoria própria.</strong><p>Crie a primeira categoria deste modo para começar.</p></div>
          ) : (
            <ul className="content-category-list">
              {categorias.map((categoria) => (
                <li key={categoria.id} className="content-category-card">
                  <div className="content-category-card__copy">
                    <div><h3>{categoria.nome}</h3><span className={categoria.ativa ? 'content-badge content-badge--active' : 'content-badge'}>{categoria.ativa ? 'Ativa' : 'Inativa'}</span></div>
                    <p>{categoria.descricao || 'Sem descrição.'}</p>
                  </div>
                  <div className="content-category-card__actions">
                    <button className="button-secondary" type="button" disabled={enviando} onClick={() => { setFormulario(categoria); setSucesso('') }}>Editar</button>
                    <button className="button-secondary" type="button" disabled={enviando} onClick={() => alternarAtiva(categoria)}>{categoria.ativa ? 'Desativar' : 'Ativar'}</button>
                    <button className="button-ghost" type="button" disabled={enviando} onClick={(evento) => abrirExclusao(categoria, evento)}>Excluir</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {!carregando && !erroCarregamento && aba === 'perguntas' && (
        <PainelPerguntas
          key={`${modo}-${versaoPerguntas}`}
          modo={modo} categorias={categorias} uso={uso}
          aoAtualizarResumo={atualizarResumo} aoExpirarSessao={aoExpirarSessao}
        />
      )}
      {!carregando && !erroCarregamento && aba === 'importar' && (
        <PainelImportacao
          key={modo}
          modo={modo}
          aoExpirarSessao={aoExpirarSessao}
          aoEstadoOperacao={setImportando}
          aoConcluir={async () => { setVersaoPerguntas((atual) => atual + 1); await carregar(modo) }}
        />
      )}
      {!carregando && !erroCarregamento && aba === 'prompt' && (
        <PainelGeradorPrompt
          key={`${modo}-${uso?.perguntas.usadas ?? 0}-${categorias.filter((item) => item.ativa && !item.excluida_em).map((item) => item.id).join('-')}`}
          modo={modo} categorias={categorias} uso={uso}
        />
      )}

      {exclusao && <ModalExclusao categoria={exclusao} enviando={enviando} erro={erroExclusao} aoConfirmar={confirmarExclusao} aoCancelar={fecharExclusao} />}
    </section>
  )
}
