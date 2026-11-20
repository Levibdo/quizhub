import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import './NemAPato.css'
import './MeuConteudo.css'

import TelaJogador from './components/TelaJogador'
import TelaInicial from './components/TelaInicial'
import TelaMenuJogos from './components/TelaMenuJogos'
import TelaCategorias from './components/TelaCategorias'
import TelaQuiz from './components/TelaQuiz'
import TelaResultado from './components/TelaResultado'
import TelaRanking from './components/TelaRanking'
import TelaLogin from './components/TelaLogin'
import TelaCadastro from './components/TelaCadastro'
import TelaNemAPato from './components/TelaNemAPato'
import TelaMeuConteudo from './components/TelaMeuConteudo'
import TelaAdmin from './components/TelaAdmin'
import AppShell from './components/layout/AppShell'
import useModalAcessivel from './hooks/useModalAcessivel'
import { criarPartida, obterPartida, enviarResposta, avancarPergunta, cadastrarUsuario, login, logout, obterUsuarioAtual, listarCategoriasJogaveis } from './services/api'
import { limparPartidaClassicaAtiva, obterPartidaClassicaAtiva, partidaIdDaRota, salvarPartidaClassicaAtiva } from './utils/partidaClassica'

const TEMPO_POR_PERGUNTA = 15
const TOTAL_PERGUNTAS = 10
const ROTAS_TELA = {
  inicio: '/', jogos: '/jogos', login: '/login', cadastro: '/cadastro', jogador: '/jogador',
  categorias: '/categorias', ranking: '/ranking', 'meu-conteudo': '/meu-conteudo',
  admin: '/admin',
  jogando: '/quiz', resultado: '/resultado',
}

function telaDaLocalizacao() {
  if (window.location.pathname?.startsWith('/nem-a-pato')) return 'nem-pato'
  if (window.location.pathname === '/quiz' || window.location.pathname?.startsWith('/quiz/')) return 'jogando'
  const encontrada = Object.entries(ROTAS_TELA).find(([, caminho]) => caminho === window.location.pathname)?.[0] ?? 'inicio'
  return ['categorias', 'resultado'].includes(encontrada) ? 'inicio' : encontrada
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
  const [recuperandoPartida, setRecuperandoPartida] = useState(false)
  const [erroRecuperacao, setErroRecuperacao] = useState('')
  const [tentativaRecuperacao, setTentativaRecuperacao] = useState(0)
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
  const [loginAdministrativo, setLoginAdministrativo] = useState(tela === 'admin')
  const acaoMarcaNemPatoRef = useRef(null)
  const acaoMarcaMeuConteudoRef = useRef(null)
  const protecaoNavegacaoAdminRef = useRef(null)
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

  const navegar = useCallback((destino, { substituir = false, registrar = true, caminho: caminhoInformado } = {}) => {
    versaoNavegacaoRef.current += 1
    if (!['admin', 'login'].includes(destino)) setLoginAdministrativo(false)
    setErro('')
    setErroAuth('')
    if (registrar && destino !== 'nem-pato') {
      const caminho = caminhoInformado ?? ROTAS_TELA[destino] ?? '/'
      if (window.location.pathname !== caminho) {
        const posicao = substituir ? posicaoHistoricoRef.current : posicaoHistoricoRef.current + 1
        window.history[substituir ? 'replaceState' : 'pushState']({ quizhubTela: destino, quizhubPosicao: posicao }, '', caminho)
        posicaoHistoricoRef.current = posicao
      }
    }
    setTela(destino)
  }, [])

  const aplicarPartidaRecuperada = useCallback((recuperada) => {
    if (recuperada.fase === 'EXPIRADA') {
      limparPartidaClassicaAtiva()
      setPartida(null)
      setErroRecuperacao('Esta partida expirou e não pode mais ser continuada.')
      return
    }
    setCategoriaSelecionada(recuperada.categoria)
    setPartida(recuperada)
    setPerguntaAtual(Math.max(0, (recuperada.ordem_atual ?? 1) - 1))
    const prazo = Date.parse(recuperada.prazo_resposta_em ?? '')
    setTempoRestante(Number.isFinite(prazo)
      ? Math.max(0, Math.ceil((prazo - Date.now()) / 1000))
      : TEMPO_POR_PERGUNTA)
    if (recuperada.fase === 'AGUARDANDO_AVANCO') {
      setRespostaSelecionada(recuperada.resultado_ultima_resposta?.alternativa_selecionada ?? null)
      setResultadoResposta({ ...recuperada, ...recuperada.resultado_ultima_resposta })
      respostaConfirmadaRef.current = true
    } else {
      setRespostaSelecionada(null)
      setResultadoResposta(null)
      respostaConfirmadaRef.current = false
    }
    timeoutEnviadoRef.current = false
    if (recuperada.fase === 'FINALIZADA') {
      limparPartidaClassicaAtiva()
      navegar('resultado', { substituir: true })
    }
  }, [navegar])

  const sincronizarPartida = useCallback(async (partidaId) => {
    const recuperada = await obterPartida(partidaId)
    salvarPartidaClassicaAtiva(partidaId)
    aplicarPartidaRecuperada(recuperada)
    return recuperada
  }, [aplicarPartidaRecuperada])

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
      } else if (error.status === 401 && loginAdministrativo) {
        navegar('login', { substituir: true })
        setErroAuth('Entre com uma conta administrativa para continuar.')
      }
    })
    return () => { ativo = false }
  }, [loginAdministrativo, navegar, tentativaSessao])

  useEffect(() => {
    if (!window.history.state?.quizhubTela && tela !== 'nem-pato') {
      const caminho = tela === 'jogando' ? window.location.pathname : ROTAS_TELA[tela] ?? '/'
      window.history.replaceState?.({ quizhubTela: tela, quizhubPosicao: posicaoHistoricoRef.current }, '', caminho)
    }
  }, [tela])

  useEffect(() => {
    if (tela !== 'jogando' || partida) return undefined
    if (statusSessao === 'carregando' || statusSessao === 'erro') return undefined
    let ativo = true
    Promise.resolve().then(async () => {
      if (!ativo) return
      const partidaRota = partidaIdDaRota()
      const partidaId = partidaRota ?? obterPartidaClassicaAtiva()
      if (!partidaId) {
        navegar('inicio', { substituir: true })
        return
      }
      if (!partidaRota) {
        navegar('jogando', { substituir: true, caminho: `/quiz/${partidaId}` })
      }
      setRecuperandoPartida(true)
      setErroRecuperacao('')
      try {
        await sincronizarPartida(partidaId)
      } catch (error) {
        if (!ativo) return
        if (error.status === 401) {
          setErroRecuperacao('Sua sessão ou identidade de visitante expirou. Entre novamente para continuar.')
        } else if (error.status === 404) {
          if (obterPartidaClassicaAtiva() === partidaId) {
            limparPartidaClassicaAtiva()
          }
          setErroRecuperacao('Partida inexistente ou inacessível para este jogador.')
        } else {
          setErroRecuperacao(`Não foi possível recuperar a partida. ${error.message}`)
        }
      } finally {
        if (ativo) setRecuperandoPartida(false)
      }
    })
    return () => { ativo = false }
  }, [navegar, partida, statusSessao, sincronizarPartida, tela, tentativaRecuperacao])

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

  const registrarProtecaoNavegacaoAdmin = useCallback((acao) => {
    protecaoNavegacaoAdminRef.current = acao
  }, [])

  const executarNavegacao = useCallback((acao) => {
    if (tela === 'admin' && protecaoNavegacaoAdminRef.current) protecaoNavegacaoAdminRef.current(acao)
    else acao()
  }, [tela])

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
    if (tela === 'admin' && protecaoNavegacaoAdminRef.current) {
      protecaoNavegacaoAdminRef.current(() => navegar('inicio'))
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
    if (tela !== 'ranking') return undefined
    let ativo = true
    Promise.resolve().then(() => {
      if (ativo) carregarCategorias()
    })
    return () => { ativo = false }
  }, [carregarCategorias, tela])

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
      const adminBloqueado = destino === 'admin' && statusSessao === 'anonimo'
      if (conteudoPrivadoBloqueado || adminBloqueado) destino = 'login'
      const posicaoDestino = Number.isInteger(evento.state?.quizhubPosicao) ? evento.state.quizhubPosicao : null
      const deslocamento = posicaoDestino === null ? null : posicaoDestino - posicaoHistoricoRef.current
      const aplicar = () => {
        if (posicaoDestino !== null) posicaoHistoricoRef.current = posicaoDestino
        if (rotaSemEstado && window.location.pathname !== ROTAS_TELA.inicio) navegar(destino, { substituir: true })
        else if (destino === 'login' && window.location.pathname !== ROTAS_TELA.login) navegar(destino, { substituir: true })
        else navegar(destino, { registrar: false })
        if (conteudoPrivadoBloqueado) setErroAuth('Entre para acessar seu conteúdo.')
        if (adminBloqueado) {
          setLoginAdministrativo(true)
          setErroAuth('Entre com uma conta administrativa para continuar.')
        }
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
      } else if (tela === 'admin' && protecaoNavegacaoAdminRef.current) {
        protecaoNavegacaoAdminRef.current(aplicar)
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

  function abrirAdministracao() {
    setLoginAdministrativo(true)
    if (!usuario) {
      navegar('login')
      setErroAuth('Entre com uma conta administrativa para continuar.')
      return
    }
    navegar('admin')
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
      if (versaoNavegacao === versaoNavegacaoRef.current) {
        if (loginAdministrativo) navegar('admin')
        else navegar('jogos')
      }
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
      setLoginAdministrativo(false)
      setStatusSessao('anonimo')
      setJogador('')
      setPartida(null)
      limparPartidaClassicaAtiva()
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
      resultadoSalvoRef.current = true
    }
    navegar('resultado')
  }, [navegar])

  function abrirRanking() {
    navegar('ranking')
  }

  async function iniciarQuiz(categoria) {
    if (enviandoRef.current) return

    enviandoRef.current = true
    setRequisicaoEmAndamento(true)
    setErro('')
    const versaoNavegacao = versaoNavegacaoRef.current
    try {
      const novaPartida = await criarPartida(
        usuario ? undefined : jogador,
        categoria,
      )
      if (versaoNavegacao !== versaoNavegacaoRef.current) return
      setCategoriaSelecionada(novaPartida.categoria)
      setPartida(novaPartida)
      salvarPartidaClassicaAtiva(novaPartida.partida_id)
      setPerguntaAtual(0)
      setTempoRestante(TEMPO_POR_PERGUNTA)
      setRespostaSelecionada(null)
      setResultadoResposta(null)
      timeoutEnviadoRef.current = false
      resultadoSalvoRef.current = false
      respostaConfirmadaRef.current = false
      navegar('jogando', { caminho: `/quiz/${novaPartida.partida_id}` })
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
      if (error.status === 409 && partida?.partida_id) {
        try {
          await sincronizarPartida(partida.partida_id)
          return
        } catch (sincronizacao) {
          setErro(`Não foi possível sincronizar a partida. ${sincronizacao.message}`)
        }
      }
      setErro(error.message)
      setRespostaSelecionada(null)
    } finally {
      enviandoRef.current = false
      setRequisicaoEmAndamento(false)
    }
  }, [partida, resultadoResposta, sincronizarPartida])

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
    limparPartidaClassicaAtiva()
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
        limparPartidaClassicaAtiva()
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
      if (error.status === 409 && partida?.partida_id) {
        try {
          await sincronizarPartida(partida.partida_id)
          return
        } catch (sincronizacao) {
          setErro(`Não foi possível sincronizar a partida. ${sincronizacao.message}`)
        }
      }
      setErro(error.message)
    } finally {
      avancandoRef.current = false
      setAvancando(false)
    }
  }

  const pergunta = partida?.pergunta_atual

  return (
    <AppShell
      imersivo={tela === 'nem-pato'}
      aoClicarMarca={clicarMarca}
      usuario={statusSessao === 'autenticado' ? usuario : null}
      navegacao={{
        tela,
        bloqueado: authCarregando || statusSessao === 'carregando',
        inicio: () => executarNavegacao(() => navegar('inicio')),
        jogos: () => executarNavegacao(() => navegar('jogos')),
        ranking: () => executarNavegacao(abrirRanking),
        entrar: () => executarNavegacao(() => navegar('login')),
        cadastrar: () => executarNavegacao(() => navegar('cadastro')),
        meuConteudo: () => executarNavegacao(abrirMeuConteudo),
        administrar: () => executarNavegacao(abrirAdministracao),
        sair: () => executarNavegacao(() => sair()),
      }}
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
          convidado={() => navegar('jogos')}
          entrar={() => navegar('login')}
          continuarJogos={() => navegar('jogos')}
        />
      )}
      {tela === 'jogos' && (
        <TelaMenuJogos
          bloqueado={authCarregando || statusSessao === 'carregando' || statusSessao === 'erro'}
          jogar={jogarAtual}
          verRanking={abrirRanking}
          nemAPato={abrirNemAPato}
        />
      )}
      {tela === 'meu-conteudo' && usuario && (
        <TelaMeuConteudo voltar={() => navegar('inicio')} aoExpirarSessao={expirarSessaoMeuConteudo} registrarAcaoMarca={registrarAcaoMarcaMeuConteudo} />
      )}
      {tela === 'admin' && usuario?.perfil === 'ADMIN' && (
        <TelaAdmin voltar={() => { setLoginAdministrativo(false); navegar('inicio') }} aoExpirarSessao={expirarSessaoMeuConteudo} registrarProtecaoNavegacao={registrarProtecaoNavegacaoAdmin} />
      )}
      {tela === 'admin' && usuario && usuario.perfil !== 'ADMIN' && (
        <section className="admin-screen" aria-labelledby="admin-negado-title">
          <div className="admin-panel" role="alert">
            <h1 id="admin-negado-title">Acesso negado</h1>
            <p>Seu usuário não possui permissão administrativa.</p>
            <button className="button-secondary" onClick={() => { setLoginAdministrativo(false); navegar('inicio') }}>Voltar ao início</button>
          </div>
        </section>
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
          carregando={authCarregando} erro={erroAuth}
          administrativo={loginAdministrativo} />
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
          totalPerguntas={partida.total_perguntas ?? TOTAL_PERGUNTAS}
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
      {tela === 'jogando' && !pergunta && (
        <section className="quiz-recovery" aria-labelledby="quiz-recovery-title">
          <section className="quiz-recovery-card">
            <h1 id="quiz-recovery-title">
              {recuperandoPartida ? 'Recuperando sua partida…' : 'Não foi possível abrir a partida'}
            </h1>
            {recuperandoPartida ? (
              <p role="status">Aguarde enquanto sincronizamos o progresso salvo.</p>
            ) : (
              <>
                <p role="alert">{erroRecuperacao || 'Não há uma partida ativa para recuperar.'}</p>
                {erroRecuperacao && !erroRecuperacao.includes('inacessível') && !erroRecuperacao.includes('expirou') && (
                  <button type="button" onClick={() => setTentativaRecuperacao((valor) => valor + 1)}>
                    Tentar novamente
                  </button>
                )}
                <button type="button" className="button-secondary" onClick={() => navegar('inicio', { substituir: true })}>
                  Voltar ao início
                </button>
              </>
            )}
          </section>
        </section>
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
