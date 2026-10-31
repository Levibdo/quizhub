import { useCallback, useEffect, useState } from 'react'
import {
  aprovarRascunhoEditorial, decidirAvisoRevisao, decidirPerguntaRevisao,
  devolverRascunhoEdicao, encaminharRascunhoRevisao, listarAvisosRevisao,
  listarPerguntasRevisao, obterHistoricoRevisaoPergunta,
  obterPerguntaRascunho, obterRevisaoRascunho, reabrirRascunhoEditorial,
  solicitarCorrecaoRascunho, verificarFonteRevisao, validarRascunhoOficial,
  publicarRascunhoEditorial,
} from '../services/api'

const ROTULO = { PENDENTE: 'Pendente', APROVADA: 'Aprovada', CORRECAO_SOLICITADA: 'Correção solicitada', REPROVADA: 'Reprovada' }
const validaTexto = (valor, minimo = 10) => valor.trim().length >= minimo
const erroEditorial = (erro) => ({
  401: 'Sua sessão terminou. Entre novamente para continuar.',
  403: 'A operação foi recusada. Confirme sua permissão administrativa e tente novamente.',
  409: `Conflito de estado: ${erro.message}`,
  412: 'A revisão mudou no servidor. Os dados preenchidos foram preservados; atualize antes de reenviar.',
  422: `Critério editorial não atendido: ${erro.message}`,
  428: 'A revisão obrigatória não foi informada. Atualize os dados antes de tentar novamente.',
}[erro.status] || erro.message)

function PublicacaoRascunho({ rascunho, revisao, ocupado, aoPublicar, aoAlterar }) {
  const [justificativa, setJustificativa] = useState('')
  const [confirmado, setConfirmado] = useState(false)
  const [validacao, setValidacao] = useState(null)
  const [erro, setErro] = useState('')
  useEffect(() => {
    let ativo = true
    validarRascunhoOficial(rascunho.id).then((resultado) => { if (ativo) setValidacao(resultado) }).catch((e) => { if (ativo) setErro(erroEditorial(e)) })
    return () => { ativo = false }
  }, [rascunho.id])
  const valido = validaTexto(justificativa) && confirmado && validacao?.resumo?.erros === 0
  return <section className="admin-publication" aria-labelledby="admin-publication-title">
    <div className="admin-section-heading"><div><span className="admin-draft-badge">PUBLICAÇÃO INCREMENTAL</span><h5 id="admin-publication-title">Publicar nova versão oficial</h5></div><span className="admin-status">APROVADO</span></div>
    <p>A publicação cria uma nova versão completa e preserva a versão ativa anterior e todo o histórico.</p>
    <dl className="admin-publication-summary"><div><dt>Total final</dt><dd>{rascunho.total_perguntas}</dd></div><div><dt>Adicionadas</dt><dd>{rascunho.adicionadas}</dd></div><div><dt>Modificadas</dt><dd>{rascunho.modificadas}</dd></div><div><dt>Revisadas neste ciclo</dt><dd>{Object.values(revisao.contagens || {}).reduce((soma, valor) => soma + valor, 0)}</dd></div><div><dt>Erros estruturais</dt><dd>{validacao?.resumo?.erros ?? '…'}</dd></div></dl>
    {erro && <p className="admin-error" role="alert">{erro}</p>}
    <label>Justificativa da publicação<textarea value={justificativa} minLength="10" required onChange={(e) => { setJustificativa(e.target.value); aoAlterar(true) }} /></label>
    <label className="admin-draft-check"><input type="checkbox" checked={confirmado} onChange={(e) => { setConfirmado(e.target.checked); aoAlterar(true) }} /> Confirmo que esta versão foi revisada e substituirá a versão ativa.</label>
    <button type="button" disabled={ocupado || !valido} onClick={() => aoPublicar(justificativa.trim())}>Publicar e ativar nova versão</button>
  </section>
}

function DecisaoPergunta({ ocupado, aoEnviar, aoAlterar }) {
  const [decisao, setDecisao] = useState('APROVADA')
  const [justificativa, setJustificativa] = useState('')
  const [relacao, setRelacao] = useState('')
  return <form className="admin-review-form" onSubmit={(e) => { e.preventDefault(); if (validaTexto(justificativa)) aoEnviar({ decisao, justificativa, relacao_fontes_resposta: relacao || null }) }}>
    <label>Decisão<select value={decisao} onChange={(e) => { setDecisao(e.target.value); aoAlterar() }}><option value="APROVADA">Aprovar pergunta</option><option value="CORRECAO_SOLICITADA">Solicitar correção</option><option value="REPROVADA">Reprovar pergunta</option></select></label>
    <label>Justificativa<textarea value={justificativa} onChange={(e) => { setJustificativa(e.target.value); aoAlterar() }} minLength="10" required /></label>
    <label>Relação entre fontes e resposta<textarea value={relacao} onChange={(e) => { setRelacao(e.target.value); aoAlterar() }} /></label>
    <button type="submit" disabled={ocupado || !validaTexto(justificativa)}>Registrar decisão</button>
  </form>
}

function Fonte({ fonte, ocupado, aoEnviar, aoAlterar }) {
  const [resultado, setResultado] = useState('CONSULTADA')
  const [evidencia, setEvidencia] = useState('')
  const [relacao, setRelacao] = useState('')
  const [observacoes, setObservacoes] = useState('')
  const valido = validaTexto(evidencia) && (resultado !== 'SUFICIENTE' || validaTexto(relacao))
  if (fonte.id === undefined || fonte.id === null) return <article className="admin-review-source"><div><strong>{fonte.titulo}</strong><a href={fonte.url} target="_blank" rel="noreferrer">Abrir referência</a><small>Acesso: {fonte.acessada_em}</small></div><p className="admin-warning">O contrato de detalhe não fornece o identificador desta fonte; a verificação não pode ser registrada com segurança.</p></article>
  return <form className="admin-review-source" onSubmit={(e) => { e.preventDefault(); if (valido) aoEnviar(fonte.id, { resultado, evidencia_documental: evidencia, relacao_com_resposta: relacao || null, justificativa: observacoes || null }) }}>
    <div><strong>{fonte.titulo}</strong><a href={fonte.url} target="_blank" rel="noreferrer">Abrir referência</a><small>Acesso: {fonte.acessada_em}</small></div>
    <label>Resultado<select value={resultado} onChange={(e) => { setResultado(e.target.value); aoAlterar() }}><option>CONSULTADA</option><option>SUFICIENTE</option><option>INSUFICIENTE</option><option>REJEITADA</option></select></label>
    <label>Evidência documental<textarea value={evidencia} onChange={(e) => { setEvidencia(e.target.value); aoAlterar() }} minLength="10" required /></label>
    <label>Como sustenta a resposta<textarea value={relacao} onChange={(e) => { setRelacao(e.target.value); aoAlterar() }} required={resultado === 'SUFICIENTE'} /></label>
    <label>Observações<textarea value={observacoes} onChange={(e) => { setObservacoes(e.target.value); aoAlterar() }} /></label>
    <button type="submit" disabled={ocupado || !valido}>Registrar verificação</button>
  </form>
}

function Avisos({ rascunho, revisao, avisos, ocupado, aoExecutar, aoFiltrar }) {
  const decidir = (aviso, decisao) => {
    const justificativa = window.prompt(`Justificativa para marcar o aviso como ${decisao.toLowerCase()}:`)
    if (!justificativa || !validaTexto(justificativa)) return
    aoExecutar(() => decidirAvisoRevisao(
      rascunho.id, aviso.id, { decisao, justificativa: justificativa.trim() },
      revisao.revisao_conteudo, revisao.revisao_editorial,
    ), 'Confirmar a decisão sobre este aviso?')
  }
  return <section className="admin-review-warnings" aria-labelledby="review-warnings-title">
    <div className="admin-section-heading"><div><h5 id="review-warnings-title">Avisos da validação</h5><p>{avisos.total_pendencias} pendência(s) no ciclo atual</p></div><label>Estado<select onChange={(e) => aoFiltrar(e.target.value)} defaultValue=""><option value="">Todos</option><option value="PENDENTE">Pendentes</option><option value="ACEITO">Aceitos</option><option value="REJEITADO">Rejeitados</option></select></label></div>
    {!avisos.itens.length ? <p className="admin-empty">Nenhum aviso neste filtro.</p> : <div className="admin-review-list">{avisos.itens.map((aviso) => <article key={aviso.id}><div><strong>{aviso.codigo}</strong><span className="admin-status">{aviso.decisao || 'PENDENTE'}</span></div><p>{aviso.id_editorial || 'Catálogo'}{aviso.campo ? ` · ${aviso.campo}` : ''}</p><p>{aviso.mensagem}</p>{aviso.recomendacao && <small>{aviso.recomendacao}</small>}{aviso.decisao ? <small>Justificativa: {aviso.justificativa}</small> : <div><button type="button" disabled={ocupado} onClick={() => decidir(aviso, 'ACEITO')}>Aceitar aviso</button><button type="button" className="button-secondary" disabled={ocupado} onClick={() => decidir(aviso, 'REJEITADO')}>Rejeitar aviso</button></div>}</article>)}</div>}
  </section>
}

function Detalhe({ rascunho, item, revisao, aoFechar, aoAtualizar, aoErro, aoSujo }) {
  const [pergunta, setPergunta] = useState(null)
  const [historico, setHistorico] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  useEffect(() => { Promise.all([obterPerguntaRascunho(rascunho.id, item.pergunta_id), obterHistoricoRevisaoPergunta(rascunho.id, item.pergunta_id)]).then(([p, h]) => { setPergunta(p); setHistorico(h) }).catch(aoErro) }, [aoErro, item.pergunta_id, rascunho.id])
  const executar = async (acao) => { setOcupado(true); aoSujo(true); try { await acao(); aoSujo(false); await aoAtualizar(); aoFechar() } catch (erro) { aoErro(erro) } finally { setOcupado(false) } }
  if (!pergunta || !historico) return <p className="admin-loading" role="status">Carregando revisão da pergunta…</p>
  const eventos = [...historico.decisoes.map((x) => ({ ...x, tipo: x.decisao, texto: x.justificativa })), ...historico.verificacoes_fontes.map((x) => ({ ...x, tipo: `Fonte: ${x.resultado}`, texto: x.evidencia_documental }))]
  return <section className="admin-review-detail" aria-labelledby="review-question-title">
    <div className="admin-section-heading"><div><span className="admin-draft-badge">RASCUNHO — NÃO PUBLICADO</span><h4 id="review-question-title">{pergunta.id_editorial}</h4></div><button type="button" className="button-secondary" onClick={aoFechar}>Voltar à lista</button></div>
    <p className="admin-status">{ROTULO[item.estado]} · revisão editorial {item.revisao_editorial}</p><h5>{pergunta.enunciado}</h5>
    {rascunho.modo === 'QUIZ_CLASSICO' ? <><ol className="admin-question-alternatives">{pergunta.alternativas.map((alt, i) => <li key={i} className={i === pergunta.alternativa_correta ? 'is-correct' : ''}>{alt}{i === pergunta.alternativa_correta && <strong>Resposta correta</strong>}</li>)}</ol><p>Dificuldade: {pergunta.dificuldade}</p></> : <dl className="admin-question-answer"><div><dt>Resposta numérica</dt><dd><code>{String(pergunta.resposta_numerica)}</code></dd></div><div><dt>Unidade</dt><dd>{pergunta.unidade || 'Não informada'}</dd></div><div><dt>Natureza</dt><dd>{pergunta.natureza_resposta}</dd></div><div><dt>Qualificação</dt><dd>{pergunta.qualificacao_estimativa || 'Não informada'}</dd></div></dl>}
    <section><h5>Explicação</h5><p>{pergunta.explicacao}</p></section>
    <section><h5>Verificação das fontes</h5>{pergunta.referencias.map((fonte) => <Fonte key={fonte.id} fonte={fonte} ocupado={ocupado} aoAlterar={() => aoSujo(true)} aoEnviar={(fonteId, dados) => executar(() => verificarFonteRevisao(rascunho.id, item.pergunta_id, fonteId, dados, revisao.revisao_conteudo, item.revisao_editorial))} />)}</section>
    <DecisaoPergunta ocupado={ocupado} aoAlterar={() => aoSujo(true)} aoEnviar={(dados) => executar(() => decidirPerguntaRevisao(rascunho.id, item.pergunta_id, dados, revisao.revisao_conteudo, item.revisao_editorial))} />
    <section className="admin-draft-history"><h5>Histórico factual</h5>{!eventos.length ? <p className="admin-empty">Nenhuma decisão registrada.</p> : <ol>{eventos.map((x) => <li key={x.id}><strong>{x.tipo}</strong><span>{x.texto}</span><small>{new Date(x.criada_em).toLocaleString('pt-BR')}</small></li>)}</ol>}</section>
  </section>
}

export default function AdminRevisaoRascunho({ rascunho, aoSincronizar, aoExpirarSessao, aoAlterarFormulario }) {
  const [revisao, setRevisao] = useState(null); const [lista, setLista] = useState(null)
  const [avisos, setAvisos] = useState(null); const [estadoAviso, setEstadoAviso] = useState('')
  const [estado, setEstado] = useState(''); const [pagina, setPagina] = useState(1)
  const [detalhe, setDetalhe] = useState(null); const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false); const [sujo, setSujo] = useState(false)
  const tratarErro = useCallback((e) => { if (e.status === 401) aoExpirarSessao(); else setErro(erroEditorial(e)) }, [aoExpirarSessao])
  const carregar = async (p = pagina) => { const [r, l, a] = await Promise.all([obterRevisaoRascunho(rascunho.id), listarPerguntasRevisao(rascunho.id, { pagina: p, limite: 20, estado }), listarAvisosRevisao(rascunho.id, { pagina: 1, limite: 100, estado: estadoAviso, severidade: 'AVISO' })]); setRevisao(r); setLista(l); setAvisos(a); setPagina(p) }
  useEffect(() => {
    if (rascunho.status === 'EM_EDICAO') return undefined
    let ativo = true
    Promise.all([
      obterRevisaoRascunho(rascunho.id),
      listarPerguntasRevisao(rascunho.id, { pagina: 1, limite: 20, estado }),
      listarAvisosRevisao(rascunho.id, { pagina: 1, limite: 100, estado: estadoAviso, severidade: 'AVISO' }),
    ]).then(([r, l, a]) => { if (ativo) { setRevisao(r); setLista(l); setAvisos(a); setPagina(1) } })
      .catch((e) => { if (ativo) { if (e.status === 401) aoExpirarSessao(); else setErro(erroEditorial(e)) } })
    return () => { ativo = false }
  }, [aoExpirarSessao, estado, estadoAviso, rascunho.id, rascunho.status])
  useEffect(() => { aoAlterarFormulario?.(sujo); return () => aoAlterarFormulario?.(false) }, [aoAlterarFormulario, sujo])
  useEffect(() => {
    if (!sujo) return undefined
    const impedir = (evento) => { evento.preventDefault(); evento.returnValue = '' }
    window.addEventListener('beforeunload', impedir)
    return () => window.removeEventListener('beforeunload', impedir)
  }, [sujo])
  const executar = async (acao, confirmacao) => { if (confirmacao && !window.confirm(confirmacao)) return; setOcupado(true); setErro(''); try { await acao(); setSujo(false); await aoSincronizar(); if (rascunho.status !== 'EM_EDICAO') await carregar(1) } catch (e) { tratarErro(e) } finally { setOcupado(false) } }
  const justificar = (mensagem, acao) => { const texto = window.prompt(mensagem); if (texto && validaTexto(texto)) { setSujo(true); executar(() => acao(texto.trim()), 'Confirmar esta transição editorial?') } }
  if (rascunho.status === 'EM_EDICAO') return <section className="admin-review-start"><h4>Revisão editorial</h4><p>Valide o rascunho antes de encaminhá-lo. Durante a revisão, o conteúdo fica bloqueado para edição.</p><button type="button" disabled={ocupado} onClick={() => executar(() => encaminharRascunhoRevisao(rascunho.id, rascunho.revisao), 'Encaminhar para revisão factual?')}>Encaminhar para revisão</button>{erro && <p className="admin-error" role="alert">{erro}</p>}</section>
  if (!revisao || !lista || !avisos) return <p className="admin-loading" role="status">Carregando ciclo editorial…</p>
  if (detalhe) return <Detalhe rascunho={rascunho} item={detalhe} revisao={revisao} aoFechar={() => { if (!sujo || window.confirm('Descartar dados ainda não enviados?')) setDetalhe(null) }} aoAtualizar={() => carregar(pagina)} aoErro={tratarErro} aoSujo={setSujo} />
  const totalPaginas = Math.max(1, Math.ceil(lista.total / lista.limite)); const contagens = revisao.contagens || {}
  return <section className="admin-review-dashboard" aria-labelledby="review-dashboard-title">
    <div className="admin-section-heading"><div><span className="admin-draft-badge">RASCUNHO — NÃO PUBLICADO</span><h4 id="review-dashboard-title">Revisão factual</h4></div><span className="admin-status">{rascunho.status}</span></div>
    {rascunho.status === 'APROVADO' && <p className="admin-success">Revisão factual concluída. Este rascunho ainda não foi publicado nem ativado.</p>}{rascunho.status === 'PUBLICADO' && <p className="admin-success">Publicação confirmada pelo servidor. A nova versão oficial está ativa.</p>}{erro && <p className="admin-error" role="alert">{erro}</p>}
    <dl className="admin-review-summary"><div><dt>Total</dt><dd>{lista.total}</dd></div>{Object.keys(ROTULO).map((x) => <div key={x}><dt>{ROTULO[x]}</dt><dd>{contagens[x] || 0}</dd></div>)}</dl>
    {!revisao.elegivel_aprovacao && <section className="admin-review-blockers"><h5>Impedimentos para aprovação</h5><ul>{revisao.impedimentos_aprovacao.map((item) => <li key={item.codigo}><strong>{item.codigo}</strong> ({item.quantidade}): {item.mensagem}</li>)}</ul></section>}
    <div className="admin-draft-toolbar"><label>Estado<select value={estado} onChange={(e) => setEstado(e.target.value)}><option value="">Todos</option>{Object.entries(ROTULO).map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select></label><button type="button" className="button-secondary" onClick={() => carregar(pagina)}>Atualizar</button>{rascunho.status === 'EM_REVISAO' && <><button type="button" disabled={!lista.itens.some((x) => x.estado !== 'APROVADA')} onClick={() => justificar('Justificativa da correção:', (j) => solicitarCorrecaoRascunho(rascunho.id, { justificativa: j, perguntas: lista.itens.filter((x) => x.estado !== 'APROVADA').map((x) => x.pergunta_id) }, revisao.revisao_conteudo, revisao.revisao_editorial))}>Solicitar correção das pendentes</button><button type="button" className="button-secondary" onClick={() => justificar('Justificativa para devolver à edição:', (j) => devolverRascunhoEdicao(rascunho.id, { justificativa: j }, revisao.revisao_conteudo, revisao.revisao_editorial))}>Devolver à edição</button>{revisao.elegivel_aprovacao === true && <button type="button" onClick={() => { const justificativa = revisao.exige_justificativa_autorrevisao ? window.prompt('Justifique a autorrevisão (mínimo 20 caracteres):') : null; if (!revisao.exige_justificativa_autorrevisao || (justificativa && validaTexto(justificativa, 20))) executar(() => aprovarRascunhoEditorial(rascunho.id, { confirmacao_explicita: true, justificativa_autorrevisao: justificativa?.trim() || null }, revisao.revisao_conteudo, revisao.revisao_editorial), 'Aprovar editorialmente? Isto não publica nem ativa o catálogo.') }}>Aprovar revisão factual</button>}</>}{rascunho.status === 'APROVADO' && <button type="button" onClick={() => justificar('Justificativa para reabrir:', (j) => reabrirRascunhoEditorial(rascunho.id, { justificativa: j }, revisao.revisao_conteudo))}>Reabrir para edição</button>}</div>
    <Avisos rascunho={rascunho} revisao={revisao} avisos={avisos} ocupado={ocupado} aoExecutar={executar} aoFiltrar={setEstadoAviso} />
    {rascunho.status === 'APROVADO' && <PublicacaoRascunho rascunho={rascunho} revisao={revisao} ocupado={ocupado} aoAlterar={setSujo} aoPublicar={(justificativa) => executar(() => publicarRascunhoEditorial(rascunho.id, justificativa, rascunho.revisao), 'Publicar e ativar esta versão? A versão ativa atual será arquivada.') } />}
    {!lista.itens.length ? <p className="admin-empty">Nenhuma pergunta neste filtro.</p> : <div className="admin-review-list">{lista.itens.map((item) => <article key={item.id}><div><strong>{item.id_editorial}</strong><span className="admin-status">{ROTULO[item.estado]}</span></div><p>Revisão da pergunta {item.revisao_pergunta} · editorial {item.revisao_editorial}</p><button type="button" onClick={() => setDetalhe(item)}>Revisar pergunta</button></article>)}</div>}
    <nav className="admin-pagination" aria-label="Paginação da revisão"><button type="button" className="button-secondary" disabled={pagina <= 1} onClick={() => carregar(pagina - 1)}>Anterior</button><span>Página {pagina} de {totalPaginas}</span><button type="button" className="button-secondary" disabled={pagina >= totalPaginas} onClick={() => carregar(pagina + 1)}>Próxima</button></nav>
  </section>
}
