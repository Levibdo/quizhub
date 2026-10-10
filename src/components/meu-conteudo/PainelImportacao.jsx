import { useCallback, useEffect, useRef, useState } from 'react'
import { confirmarImportacaoMeuConteudo, validarImportacaoMeuConteudo } from '../../services/api'

const FORMATOS = ['xlsx', 'csv', 'json']
const MAX_ARQUIVO = 5 * 1024 * 1024

function formatoArquivo(arquivo) {
  return arquivo?.name.split('.').pop()?.toLowerCase() ?? ''
}

function tamanhoLegivel(bytes) {
  if (bytes < 1024) return `${bytes} bytes`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MiB`
}

function ModalConfirmacao({ quantidade, enviando, aoConfirmar, aoCancelar }) {
  const cancelarRef = useRef(null)
  useEffect(() => {
    cancelarRef.current?.focus()
    const fechar = (evento) => { if (evento.key === 'Escape' && !enviando) aoCancelar() }
    window.addEventListener?.('keydown', fechar)
    return () => window.removeEventListener?.('keydown', fechar)
  }, [aoCancelar, enviando])
  return <div className="content-dialog-backdrop" role="presentation"><section className="content-dialog" role="dialog" aria-modal="true" aria-labelledby="import-confirm-title"><span className="content-eyebrow">Confirmação</span><h3 id="import-confirm-title">Importar {quantidade} perguntas?</h3><p>A importação será integral. Nenhum registro será criado se o servidor detectar conflito.</p><div className="content-dialog__actions"><button disabled={enviando} onClick={aoConfirmar}>{enviando ? 'Importando...' : 'Confirmar importação'}</button><button ref={cancelarRef} className="button-secondary" disabled={enviando} onClick={aoCancelar}>Cancelar</button></div></section></div>
}

function Orientacoes({ modo }) {
  const campos = modo === 'QUIZ_CLASSICO'
    ? 'categoria_id, enunciado, alternativa_a, alternativa_b, alternativa_c, alternativa_d, alternativa_correta e explicacao'
    : 'categoria_id, enunciado, resposta_numerica e explicacao; unidade e fonte são opcionais'
  return <aside className="import-guidance"><h3>Como preparar o arquivo</h3><p>XLSX e CSV usam uma linha de cabeçalho com: <strong>{campos}</strong>.</p><p>JSON deve conter uma lista de objetos com os mesmos campos. Use o UUID de uma categoria própria, ativa e deste modo. O lote deve conter de 1 a 100 registros.</p>{modo === 'QUIZ_CLASSICO' ? <p>A alternativa correta deve ser A, B, C ou D.</p> : <p>A resposta numérica deve ser um inteiro entre 0 e 9223372036854775807. No XLSX, valores acima da precisão segura devem ser evitados.</p>}</aside>
}

function PreviaRegistro({ registro, modo, indice }) {
  return <li className="import-preview__item"><span className="content-eyebrow">Registro {indice + 1}</span><h4>{registro.enunciado}</h4><p>Categoria: <code>{registro.categoria_id}</code></p>{modo === 'QUIZ_CLASSICO' ? <><p>A) {registro.alternativa_a} · B) {registro.alternativa_b} · C) {registro.alternativa_c} · D) {registro.alternativa_d}</p><p>Correta: <strong>{registro.alternativa_correta}</strong></p></> : <p>Resposta: <strong>{String(registro.resposta_numerica)}{registro.unidade ? ` ${registro.unidade}` : ''}</strong></p>}<p>{registro.explicacao}</p></li>
}

export default function PainelImportacao({ modo, aoConcluir, aoExpirarSessao, aoEstadoOperacao }) {
  const [arquivo, setArquivo] = useState(null)
  const [erroLocal, setErroLocal] = useState('')
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [previa, setPrevia] = useState(null)
  const [arquivoValidado, setArquivoValidado] = useState(null)
  const [expirada, setExpirada] = useState(false)
  const [processando, setProcessando] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const [modal, setModal] = useState(false)
  const operacaoRef = useRef(0)
  const envioRef = useRef(false)

  const invalidarPrevia = useCallback(() => {
    operacaoRef.current += 1
    setArquivoValidado(null)
    setExpirada(false)
    setPrevia(null)
    setModal(false)
    setProcessando(false)
    aoEstadoOperacao(false)
    envioRef.current = false
  }, [aoEstadoOperacao])

  useEffect(() => () => { operacaoRef.current += 1; aoEstadoOperacao(false) }, [aoEstadoOperacao])
  useEffect(() => {
    if (!previa?.expira_em) return undefined
    const atraso = Math.min(2_147_483_647, Math.max(0, Date.parse(previa.expira_em) - Date.now()))
    const timer = window.setTimeout(() => setExpirada(true), atraso)
    return () => window.clearTimeout(timer)
  }, [previa])

  function selecionar(evento) {
    const selecionado = evento.target.files?.[0] ?? null
    invalidarPrevia(); setArquivo(selecionado); setErro(''); setSucesso(''); setErroLocal('')
    if (!selecionado) return
    if (!FORMATOS.includes(formatoArquivo(selecionado))) setErroLocal('Use um arquivo XLSX, CSV ou JSON.')
    else if (selecionado.size > MAX_ARQUIVO) setErroLocal('O arquivo deve ter no máximo 5 MiB.')
  }

  async function validar() {
    if (envioRef.current || !arquivo || erroLocal) return
    invalidarPrevia(); envioRef.current = true; setProcessando(true); aoEstadoOperacao(true); setErro(''); setSucesso('')
    const operacao = operacaoRef.current
    try {
      const resultado = await validarImportacaoMeuConteudo(modo, arquivo)
      if (operacao !== operacaoRef.current) return
      setArquivoValidado(arquivo)
      setExpirada(Date.parse(resultado.expira_em) <= Date.now())
      setPrevia(resultado)
    } catch (falha) {
      if (operacao !== operacaoRef.current) return
      if (falha.status === 401) aoExpirarSessao()
      else setErro(falha.status === 413 ? 'O arquivo excede o limite de 5 MiB.' : falha.message)
    } finally {
      if (operacao === operacaoRef.current) { setProcessando(false); aoEstadoOperacao(false) }
      envioRef.current = false
    }
  }

  const podeConfirmar = Boolean(previa?.pode_confirmar && previa.token_preview && arquivo === arquivoValidado && !expirada && !processando && !confirmando)

  async function confirmar() {
    if (envioRef.current || !podeConfirmar) return
    envioRef.current = true; setConfirmando(true); aoEstadoOperacao(true); setErro('')
    const operacao = operacaoRef.current
    const mesmoArquivo = arquivo
    try {
      const resultado = await confirmarImportacaoMeuConteudo(previa.token_preview, mesmoArquivo)
      if (operacao !== operacaoRef.current) return
      setModal(false); setArquivo(null); setPrevia(null); setArquivoValidado(null)
      setSucesso(`${resultado.criadas} perguntas importadas com sucesso.`)
      await aoConcluir()
    } catch (falha) {
      if (operacao !== operacaoRef.current) return
      setModal(false)
      if (falha.status === 401) aoExpirarSessao()
      else if (falha.status === 409 || falha.status === 422) {
        invalidarPrevia()
        setErro(`${falha.message} Valide o arquivo novamente.`)
      } else setErro(falha.message)
    } finally {
      if (operacao === operacaoRef.current) { setConfirmando(false); aoEstadoOperacao(false) }
      envioRef.current = false
    }
  }

  return <section className="import-panel" aria-labelledby="import-title" aria-busy={processando || confirmando}>
    <div className="content-section-heading"><div><span className="content-eyebrow">Importação privada</span><h2 id="import-title">Importar perguntas</h2></div></div>
    <Orientacoes modo={modo} />
    <div className="import-picker"><label htmlFor="content-import-file">Arquivo XLSX, CSV ou JSON</label><input id="content-import-file" type="file" accept=".xlsx,.csv,.json" disabled={confirmando} onChange={selecionar} />{arquivo && <dl className="import-file"><div><dt>Nome</dt><dd>{arquivo.name}</dd></div><div><dt>Formato</dt><dd>{formatoArquivo(arquivo).toUpperCase()}</dd></div><div><dt>Tamanho</dt><dd>{tamanhoLegivel(arquivo.size)}</dd></div><div><dt>Modo</dt><dd>{modo === 'QUIZ_CLASSICO' ? 'Quiz Clássico' : 'Nem a Pato'}</dd></div></dl>}</div>
    {erroLocal && <p className="mensagem-erro" role="alert">{erroLocal}</p>}{erro && <p className="mensagem-erro" role="alert">{erro}</p>}{sucesso && <p className="content-message" role="status">{sucesso}</p>}
    <button type="button" disabled={!arquivo || Boolean(erroLocal) || processando || confirmando} onClick={validar}>{processando ? 'Validando...' : 'Validar arquivo'}</button>
    {previa && <section className="import-result" aria-labelledby="import-preview-title"><h3 id="import-preview-title">Resultado da validação</h3><dl className="import-summary"><div><dt>Recebidos</dt><dd>{previa.quantidade_recebida}</dd></div><div><dt>Válidos</dt><dd>{previa.quantidade_valida}</dd></div><div><dt>Inválidos</dt><dd>{previa.quantidade_invalida}</dd></div><div><dt>Quota atual</dt><dd>{previa.quota.atual}</dd></div><div><dt>Após confirmar</dt><dd>{previa.quota.apos_confirmacao}</dd></div><div><dt>Limite</dt><dd>{previa.quota.limite}</dd></div></dl>{previa.erros.length > 0 && <div className="import-errors" role="alert"><h4>Erros encontrados</h4><ul>{previa.erros.map((item, indice) => <li key={`${item.referencia?.tipo}-${item.referencia?.valor}-${item.campo}-${indice}`}><strong>{item.referencia ? `${item.referencia.tipo} ${item.referencia.valor}` : 'Arquivo'}</strong>{item.campo ? ` · ${item.campo}` : ''}: {item.mensagem}</li>)}</ul></div>}{previa.preview.length > 0 && <><h4>Prévia dos registros</h4><ol className="import-preview">{previa.preview.map((item, indice) => <PreviaRegistro key={`${item.categoria_id}-${item.enunciado}-${indice}`} registro={item} modo={modo} indice={indice} />)}</ol></>}{expirada && <p className="mensagem-erro" role="alert">A prévia expirou. Valide o arquivo novamente.</p>}<button type="button" disabled={!podeConfirmar} onClick={() => setModal(true)}>Confirmar importação</button>{!previa.pode_confirmar && <p className="content-state">Corrija todos os registros e valide novamente. A importação parcial não está disponível.</p>}</section>}
    {modal && <ModalConfirmacao quantidade={previa.quantidade_valida} enviando={confirmando} aoConfirmar={confirmar} aoCancelar={() => setModal(false)} />}
  </section>
}
