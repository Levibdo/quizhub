import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import './NemAPato.css'
import './MeuConteudo.css'

import TelaJogador from './components/TelaJogador'
import TelaInicial from './components/TelaInicial'
import TelaCategorias from './components/TelaCategorias'
import TelaQuiz from './components/TelaQuiz'
import TelaResultado from './components/TelaResultado'
import TelaRanking from './components/TelaRanking'
import TelaLogin from './components/TelaLogin'
import TelaCadastro from './components/TelaCadastro'
import TelaNemAPato from './components/TelaNemAPato'
import TelaMeuConteudo from './components/TelaMeuConteudo'
import AppShell from './components/layout/AppShell'
import useModalAcessivel from './hooks/useModalAcessivel'
import { criarPartida, enviarResposta, avancarPergunta, cadastrarUsuario, login, logout, obterUsuarioAtual, listarCategoriasJogaveis } from './services/api'
import { carregarRanking, salvarResultado } from './utils/ranking'

const TEMPO_POR_PERGUNTA = 15
const TOTAL_PERGUNTAS = 10
const ROTAS_TELA = {
  inicio: '/', login: '/login', cadastro: '/cadastro', jogador: '/jogador',
  categorias: '/categorias', ranking: '/ranking', 'meu-conteudo': '/meu-conteudo',
  jogando: '/quiz', resultado: '/resultado',
}

function telaDaLocalizacao() {
  if (window.location.pathname?.startsWith('/nem-a-pato')) return 'nem-pato'
  const encontrada = Object.entries(ROTAS_TELA).find(([, caminho]) => caminho === window.location.pathname)?.[0] ?? 'inicio'
  return ['categorias', 'jogando', 'resultado'].includes(encontrada) ? 'inicio' : encontrada
}

function App() {
  const [tela, setTela] = useState(telaDaLocalizacao)
  const [categoriaSelecionada, setCategoriaSelecionada] = useState(null)
  const [categorias, setCategorias] = useState([])
  const [carregandoCategorias, setCarregandoCategorias] = useState(false)
  const [erroCategorias, setErroCategorias] = useState('')
  const [jogador, setJogador] = useState('')
  const [partida, setPartida] = useState(null)
  const [perguntaAtual, setPerguntaAtual] = useState(0)
  const [tempoRestante, setTempoRestante] = useState(TEMPO_POR_PERGUNTA)
  const [respostaSelecionada, setRespostaSelecionada] = useState(null)
  const [resultadoResposta, setResultadoResposta] = useState(null)
  const [requisicaoEmAndamento, setRequisicaoEmAndamento] = useState(false)
  const [erro, setErro] = useState('')
  const [ranking, setRanking] = useState(carregarRanking)
  const enviandoRef = useRef(false)
  const respostaConfirmadaRef = useRef(false)
  const avancandoRef = useRef(false)
  const [avancando, setAvancando] = useState(false)
  const timeoutEnviadoRef = useRef(false)
  const resultadoSalvoRef = useRef(false)
  const [usuario, setUsuario] = useState(null)
  const [statusSessao, setStatusSessao] = useState('carregando')
  const [tentativaSessao, setTentativaSessao] = useState(0)
  const [authCarregando, setAuthCarregando] = useState(false)
  const [erroAuth, setErroAuth] = useState('')
  const authRef = useRef(false)
  const versaoSessao = useRef(0)
  const conteudoPrivadoInicialRef = useRef(tela === 'meu-conteudo')
  const acaoMarcaNemPatoRef = useRef(null)
  const acaoMarcaMeuConteudoRef = useRef(null)
  const ignorarProximoPopRef = useRef(false)
  const posicaoHistoricoRef = useRef(Number.isInteger(window.history.state?.quizhubPosicao) ? window.history.state.quizhubPosicao : 0)
  const versaoNavegacaoRef = useRef(0)
  const retornoSaidaQuizRef = useRef(null)
  const cancelarSaidaQuizRef = useRef(null)
  const [confirmarSaidaQuiz, setConfirmarSaidaQuiz] = useState(null)
  const fecharSaidaQuiz = useCallback(() => {
    setConfirmarSaidaQuiz((atual) => { atual?.aoCancelar?.(); return null })
  }, [])
  const { modalRef: modalSaidaQuizRef, aoPressionarTecla: conterFocoSaidaQuiz } = useModalAcessivel({ aberto: Boolean(confirmarSaidaQuiz), aoFechar: fecharSaidaQuiz, focoInicialRef: cancelarSaidaQuizRef, retornoFocoRef: retornoSaidaQuizRef })

  const navegar = useCallback((destino, { substituir = false, registrar = true } = {}) => {
    versaoNavegacaoRef.current += 1
    setErro('')
    setErroAuth('')
    if (registrar && destino !== 'nem-pato') {
      const caminho = ROTAS_TELA[destino] ?? '/'
      if (window.location.pathname !== caminho) {
        const posicao = substituir ? posicaoHistoricoRef.current : posicaoHistoricoRef.current + 1
        window.history[substituir ? 'replaceState' : 'pushState']({ quizhubTela: destino, quizhubPosicao: posicao }, '', caminho)
        posicaoHistoricoRef.current = posicao
      }
    }
    setTela(destino)
  }, [])

  useEffect(() => {
    const versao = ++versaoSessao.current
    let ativo = true
    obterUsuarioAtual().then((atual) => {
      if (!ativo || versao !== versaoSessao.current) return
      setUsuario(atual)
      setStatusSessao('autenticado')
    }).catch((error) => {
      if (!ativo || versao !== versaoSessao.current) return
      setStatusSessao(error.status === 401 ? 'anonimo' : 'erro')
      if (error.status === 401 && conteudoPrivadoInicialRef.current) {
        conteudoPrivadoInicialRef.current = false
        navegar('login', { substituir: true })
        setErroAuth('Entre para acessar seu conteúdo.')
      }
    })
    return () => { ativo = false }
  }, [navegar, tentativaSessao])

  useEffect(() => {
    if (!window.history.state?.quizhubTela && tela !== 'nem-pato') {
      window.history.replaceState?.({ quizhubTela: tela, quizhubPosicao: posicaoHistoricoRef.current }, '', ROTAS_TELA[tela] ?? '/')
    }
  }, [tela])

  useEffect(() => {
    if (tela === 'jogando' || tela === 'nem-pato') return
    const titulo = globalThis.document?.querySelector?.('main h1')
    if (!titulo) return
    titulo.setAttribute?.('tabindex', '-1')
    titulo.focus?.({ preventScroll: true })
  }, [tela])

  function abrirNemAPato() {
    if (!window.location.pathname?.startsWith('/nem-a-pato')) {
      const posicao = posicaoHistoricoRef.current + 1
      window.history.pushState({ quizhubTela: 'nem-pato', quizhubPosicao: posicao }, '', '/nem-a-pato')
      posicaoHistoricoRef.current = posicao
    }
    navegar('nem-pato')
  }

  function voltarDaTelaNemAPato() {
    navegar('inicio')
  }

  const registrarAcaoMarcaNemPato = useCallback((acao) => {
    acaoMarcaNemPatoRef.current = acao
  }, [])

  const registrarAcaoMarcaMeuConteudo = useCallback((acao) => {
    acaoMarcaMeuConteudoRef.current = acao
  }, [])

  function clicarMarca(event) {
    event.preventDefault()
    if (tela === 'nem-pato' && acaoMarcaNemPatoRef.current) {
      acaoMarcaNemPatoRef.current(event)
      return
    }
    if (tela === 'meu-conteudo' && acaoMarcaMeuConteudoRef.current) {
      acaoMarcaMeuConteudoRef.current(() => navegar('inicio'), event)
      return
    }
    if (tela === 'jogando' && partida) {
      retornoSaidaQuizRef.current = event.currentTarget
      setConfirmarSaidaQuiz({ aoConfirmar: abandonarQuizClassico })
      return
    }
    navegar('inicio')
  }

  const carregarCategorias = useCallback(async () => {
    setCarregandoCategorias(true)
    setErroCategorias('')
    try {
      setCategorias(await listarCategoriasJogaveis())
    } catch (error) {
      setCategorias([])
      if (error.status === 401) {
        try { await logout() } catch { /* O estado local ainda deve expirar. */ }
        setUsuario(null)
        setStatusSessao('anonimo')
        setErroCategorias('Sua sessão expirou. Entre novamente ou tente como convidado.')
      } else {
        setErroCategorias(`Não foi possível carregar as categorias. ${error.message}`)
      }
    } finally {
      setCarregandoCategorias(false)
    }
  }, [])

  useEffect(() => {
    function aoVoltarAvancar(evento) {
      if (ignorarProximoPopRef.current) { ignorarProximoPopRef.current = false; return }
      if (window.location.pathname?.startsWith('/nem-a-pato')) {
        if (Number.isInteger(evento.state?.quizhubPosicao)) posicaoHistoricoRef.current = evento.state.quizhubPosicao
        setTela('nem-pato')
        return
      }
      let destino = evento.state?.quizhubTela ?? telaDaLocalizacao()
      const rotaSemEstado = (destino === 'jogando' && (!partida?.pergunta_atual || partida.status !== 'EM_ANDAMENTO'))
        || (destino === 'resultado' && !partida)
      if (rotaSemEstado) destino = 'inicio'
      const conteudoPrivadoBloqueado = destino === 'meu-conteudo' && statusSessao === 'anonimo'
      if (conteudoPrivadoBloqueado) destino = 'login'
      const posicaoDestino = Number.isInteger(evento.state?.quizhubPosicao) ? evento.state.quizhubPosicao : null
      const deslocamento = posicaoDestino === null ? null : posicaoDestino - posicaoHistoricoRef.current
      const aplicar = () => {
        if (posicaoDestino !== null) posicaoHistoricoRef.current = posicaoDestino
        if (rotaSemEstado && window.location.pathname !== ROTAS_TELA.inicio) navegar(destino, { substituir: true })
        else if (destino === 'login' && window.location.pathname !== ROTAS_TELA.login) navegar(destino, { substituir: true })
        else navegar(destino, { registrar: false })
        if (conteudoPrivadoBloqueado) setErroAuth('Entre para acessar seu conteúdo.')
        if (destino === 'categorias') carregarCategorias()
      }
      const cancelar = () => {
        ignorarProximoPopRef.current = true
        if (deslocamento && window.history.go) window.history.go(-deslocamento)
        else window.history.forward?.()
      }
      if (tela === 'jogando' && partida && destino !== 'jogando') {
        setConfirmarSaidaQuiz({ aoConfirmar: () => { setPartida(null); setResultadoResposta(null); aplicar() }, aoCancelar: cancelar })
      } else if (tela === 'meu-conteudo' && acaoMarcaMeuConteudoRef.current) {
        acaoMarcaMeuConteudoRef.current(aplicar, null, cancelar)
      } else aplicar()
    }
    window.addEventListener?.('popstate', aoVoltarAvancar)
    return () => window.removeEventListener?.('popstate', aoVoltarAvancar)
  }, [carregarCategorias, navegar, partida, statusSessao, tela])

  function abrirCategorias() {
    setErro('')
    navegar('categorias')
    carregarCategorias()
  }

  function abrirMeuConteudo() {
    if (!usuario) {
      navegar('login')
      setErroAuth('Entre para acessar seu conteúdo.')
      return
    }
    navegar('meu-conteudo')
  }

  const expirarSessaoMeuConteudo = useCallback(() => {
    ++versaoSessao.current
    setUsuario(null)
    setStatusSessao('anonimo')
    navegar('login')
    setErroAuth('Sua sessão expirou. Entre novamente para acessar seu conteúdo.')
  }, [navegar])

  async function autenticar(tipo, ...dados) {
    if (authRef.current) return
    authRef.current = true
    ++versaoSessao.current
    setAuthCarregando(true)
    setErroAuth('')
    const versaoNavegacao = versaoNavegacaoRef.current
    try {
      const atual = await (tipo === 'login' ? login(...dados) : cadastrarUsuario(...dados))
      setUsuario(atual)
      setStatusSessao('autenticado')
      setJogador('')
      if (versaoNavegacao === versaoNavegacaoRef.current) abrirCategorias()
    } catch (error) {
      if (versaoNavegacao === versaoNavegacaoRef.current) {
        setErroAuth(error.status === 409 ? 'Este e-mail já está cadastrado.'
          : error.status === 401 ? 'E-mail ou senha inválidos.' : error.message)
      }
    } finally {
      authRef.current = false
      setAuthCarregando(false)
    }
  }

  async function sair(destino = 'inicio') {
    if (authRef.current) return
    authRef.current = true
    ++versaoSessao.current
    setAuthCarregando(true)
    setErro('')
    try {
      await logout()
      setUsuario(null)
      setStatusSessao('anonimo')
      setJogador('')
      setPartida(null)
      setResultadoResposta(null)
      setRespostaSelecionada(null)
      navegar(destino)
    } catch (error) {
      setErro(`Não foi possível encerrar a sessão. ${error.message}`)
    } finally {
      authRef.current = false
      setAuthCarregando(false)
    }
  }

  function jogarAtual() {
    if (statusSessao === 'carregando' || statusSessao === 'erro' || authRef.current) return
    if (usuario) abrirCategorias()
    else sair('jogador') // Limpa também cookies inválidos antes de jogar como convidado.
  }

  const salvarEFinalizar = useCallback((estadoFinal) => {
    setPartida(estadoFinal)
    if (!resultadoSalvoRef.current) {
      salvarResultado({
        id: Date.now(),
        jogador: estadoFinal.jogador,
        categoria: estadoFinal.categoria,
        pontuacao: estadoFinal.pontuacao,
        acertos: estadoFinal.acertos,
        erros: estadoFinal.erros,
      })
      setRanking(carregarRanking())
      resultadoSalvoRef.current = true
    }
    navegar('resultado')
  }, [navegar])

  function abrirRanking() {
    setRanking(carregarRanking())
    navegar('ranking')
    if (categorias.length === 0 && !carregandoCategorias) carregarCategorias()
  }

  async function iniciarQuiz(categoria) {
    if (enviandoRef.current) return

    enviandoRef.current = true
    setRequisicaoEmAndamento(true)
    setErro('')
    const versaoNavegacao = versaoNavegacaoRef.current
    try {
      const novaPartida = await criarPartida(usuario ? undefined : jogador, categoria)
      if (versaoNavegacao !== versaoNavegacaoRef.current) return
      setCategoriaSelecionada(novaPartida.categoria)
      setPartida(novaPartida)
      setPerguntaAtual(0)
      setTempoRestante(TEMPO_POR_PERGUNTA)
      setRespostaSelecionada(null)
      setResultadoResposta(null)
      timeoutEnviadoRef.current = false
      resultadoSalvoRef.current = false
      respostaConfirmadaRef.current = false
      navegar('jogando')
    } catch (error) {
      setErro(error.message)
      if (error.status === 401 || (usuario && error.status === 422 &&
        error.message === 'jogador é obrigatório para partidas como convidado')) {
        setUsuario(null)
        setStatusSessao('anonimo')
        setErro('Sua sessão não está disponível. Entre novamente para iniciar a partida.')
        navegar('login')
      }
    } finally {
      enviandoRef.current = false
      setRequisicaoEmAndamento(false)
    }
  }

  const responder = useCallback(async (indiceSelecionado, timeout = false) => {
    if (enviandoRef.current || respostaConfirmadaRef.current || resultadoResposta || !partida?.pergunta_atual) return

    enviandoRef.current = true
    setRequisicaoEmAndamento(true)
    setErro('')
    setRespostaSelecionada(timeout ? null : indiceSelecionado)
    try {
      const resultado = await enviarResposta(
        partida.partida_id,
        partida.pergunta_atual.id,
        indiceSelecionado,
      )
      respostaConfirmadaRef.current = true
      setResultadoResposta(resultado)
    } catch (error) {
      setErro(error.message)
      setRespostaSelecionada(null)
    } finally {
      enviandoRef.current = false
      setRequisicaoEmAndamento(false)
    }
  }, [partida, resultadoResposta])

  useEffect(() => {
    if (
      tela !== 'jogando' ||
      confirmarSaidaQuiz ||
      resultadoResposta ||
      requisicaoEmAndamento ||
      timeoutEnviadoRef.current
    ) return
    if (tempoRestante === 0) {
      timeoutEnviadoRef.current = true
      const timerTimeout = setTimeout(() => responder(0, true), 0)
      return () => clearTimeout(timerTimeout)
    }

    const timer = setTimeout(() => {
      setTempoRestante((valorAtual) => Math.max(0, valorAtual - 1))
    }, 1000)
    return () => clearTimeout(timer)
  }, [tempoRestante, tela, resultadoResposta, requisicaoEmAndamento, responder, confirmarSaidaQuiz])

  function abandonarQuizClassico() {
    setConfirmarSaidaQuiz(null)
    setPartida(null)
    setResultadoResposta(null)
    setRespostaSelecionada(null)
    navegar('inicio')
  }

  function confirmarAbandonoQuiz() {
    const acao = confirmarSaidaQuiz?.aoConfirmar
    setConfirmarSaidaQuiz(null)
    acao?.()
  }

  async function proximaPergunta() {
    if (!resultadoResposta || avancandoRef.current) return
    avancandoRef.current = true
    setAvancando(true)
    setErro('')
    try {
      if (resultadoResposta.status === 'FINALIZADA') {
        salvarEFinalizar(resultadoResposta)
        return
      }
      const proxima = await avancarPergunta(partida.partida_id, partida.pergunta_atual.id)
      setPartida(proxima)
      setPerguntaAtual((valorAtual) => valorAtual + 1)
      setTempoRestante(TEMPO_POR_PERGUNTA)
      setRespostaSelecionada(null)
      setResultadoResposta(null)
      timeoutEnviadoRef.current = false
      respostaConfirmadaRef.current = false
    } catch (error) {
      setErro(error.message)
    } finally {
      avancandoRef.current = false
      setAvancando(false)
    }
  }

  const pergunta = partida?.pergunta_atual

  return (
    <AppShell
      aoClicarMarca={clicarMarca}
      usuario={statusSessao === 'autenticado' ? usuario : null}
    >
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}
      {statusSessao === 'carregando' && <p role="status">Verificando sessão...</p>}
      {statusSessao === 'erro' && (
        <div role="alert">
          <p>Não foi possível verificar sua sessão.</p>
          <button onClick={() => {
            setStatusSessao('carregando')
            setTentativaSessao((valor) => valor + 1)
          }}>Tentar novamente</button>
        </div>
      )}
      {authCarregando && tela === 'inicio' && <p role="status">Aguarde...</p>}

      {tela === 'inicio' && (
        <TelaInicial
          usuario={usuario}
          bloqueado={authCarregando || statusSessao === 'carregando' || statusSessao === 'erro'}
          jogar={jogarAtual}
          convidado={() => sair('jogador')}
          entrar={() => navegar('login')}
          cadastrar={() => navegar('cadastro')}
          sair={() => sair()}
          verRanking={abrirRanking}
          nemAPato={abrirNemAPato}
          meuConteudo={abrirMeuConteudo}
        />
      )}
      {tela === 'meu-conteudo' && usuario && (
        <TelaMeuConteudo voltar={() => navegar('inicio')} aoExpirarSessao={expirarSessaoMeuConteudo} registrarAcaoMarca={registrarAcaoMarcaMeuConteudo} />
      )}
      {tela === 'nem-pato' && (
        <TelaNemAPato
          voltarInicio={voltarDaTelaNemAPato}
          registrarAcaoMarca={registrarAcaoMarcaNemPato}
        />
      )}
      {tela === 'login' && (
        <TelaLogin entrar={(...dados) => autenticar('login', ...dados)}
          criarConta={() => navegar('cadastro')} voltar={() => navegar('inicio')}
          carregando={authCarregando} erro={erroAuth} />
      )}
      {tela === 'cadastro' && (
        <TelaCadastro cadastrar={(...dados) => autenticar('cadastro', ...dados)}
          entrar={() => navegar('login')} voltar={() => navegar('inicio')}
          carregando={authCarregando} erro={erroAuth} />
      )}
      {tela === 'jogador' && (
        <TelaJogador
          confirmarJogador={(nome) => { setJogador(nome); abrirCategorias() }}
          voltar={() => navegar('inicio')}
        />
      )}
      {tela === 'categorias' && (
        <TelaCategorias
          categorias={categorias}
          selecionarCategoria={iniciarQuiz}
          carregando={requisicaoEmAndamento}
          carregandoCategorias={carregandoCategorias}
          erroCategorias={erroCategorias}
          tentarNovamente={carregarCategorias}
          voltarInicio={() => navegar('inicio')}
        />
      )}
      {tela === 'jogando' && pergunta && (
        <TelaQuiz
          pergunta={pergunta}
          categoria={categorias.find((item) => (
            item.origem === 'USUARIO' ? `privada:${item.id}` : item.slug
          ) === categoriaSelecionada)}
          perguntaAtual={perguntaAtual}
          totalPerguntas={TOTAL_PERGUNTAS}
          tempoTotal={TEMPO_POR_PERGUNTA}
          pontuacao={resultadoResposta?.pontuacao ?? partida.pontuacao}
          tempoRestante={tempoRestante}
          responder={responder}
          respostaSelecionada={respostaSelecionada}
          respondido={Boolean(resultadoResposta)}
          enviando={requisicaoEmAndamento}
          resultadoResposta={resultadoResposta}
          proximaPergunta={proximaPergunta}
          avancando={avancando}
        />
      )}
      {tela === 'resultado' && partida && (
        <TelaResultado
          jogador={partida.jogador}
          acertos={partida.acertos}
          erros={partida.erros}
          pontuacao={partida.pontuacao}
          categoria={categorias.find((item) => (
            item.origem === 'USUARIO' ? `privada:${item.id}` : item.slug
          ) === categoriaSelecionada)}
          iniciarQuiz={abrirCategorias}
          verRanking={abrirRanking}
          voltarInicio={() => navegar('inicio')}
        />
      )}
      {tela === 'ranking' && (
        <TelaRanking
          ranking={ranking}
          categorias={categorias}
          carregandoCategorias={carregandoCategorias}
          erroCategorias={erroCategorias}
          tentarNovamente={carregarCategorias}
          voltarInicio={() => navegar('inicio')}
          trocarJogador={jogarAtual}
        />
      )}
      {confirmarSaidaQuiz && (
        <div className="content-dialog-backdrop" role="presentation">
          <section ref={modalSaidaQuizRef} onKeyDown={conterFocoSaidaQuiz} tabIndex={-1} className="content-dialog" role="dialog" aria-modal="true" aria-labelledby="classic-exit-title" aria-describedby="classic-exit-description">
            <span className="content-eyebrow">Quiz Clássico</span>
            <h3 id="classic-exit-title">Abandonar a partida?</h3>
            <p id="classic-exit-description">Seu progresso nesta partida será perdido.</p>
            <div className="content-dialog__actions">
              <button className="content-danger" type="button" onClick={confirmarAbandonoQuiz}>Abandonar partida</button>
              <button ref={cancelarSaidaQuizRef} className="button-secondary" type="button" onClick={fecharSaidaQuiz}>Continuar jogando</button>
            </div>
          </section>
        </div>
      )}
    </AppShell>
  )
}

export default App
