import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

import TelaJogador from './components/TelaJogador'
import TelaInicial from './components/TelaInicial'
import TelaCategorias from './components/TelaCategorias'
import TelaQuiz from './components/TelaQuiz'
import TelaResultado from './components/TelaResultado'
import TelaRanking from './components/TelaRanking'
import TelaLogin from './components/TelaLogin'
import TelaCadastro from './components/TelaCadastro'
import { criarPartida, enviarResposta, avancarPergunta, cadastrarUsuario, login, logout, obterUsuarioAtual } from './services/api'
import { carregarRanking, salvarResultado } from './utils/ranking'

const TEMPO_POR_PERGUNTA = 15
const TOTAL_PERGUNTAS = 10

function App() {
  const [tela, setTela] = useState('inicio')
  const [categoriaSelecionada, setCategoriaSelecionada] = useState(null)
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
    })
    return () => { ativo = false }
  }, [tentativaSessao])

  function navegar(destino) {
    setErro('')
    setErroAuth('')
    setTela(destino)
  }

  async function autenticar(tipo, ...dados) {
    if (authRef.current) return
    authRef.current = true
    ++versaoSessao.current
    setAuthCarregando(true)
    setErroAuth('')
    try {
      const atual = await (tipo === 'login' ? login(...dados) : cadastrarUsuario(...dados))
      setUsuario(atual)
      setStatusSessao('autenticado')
      setJogador('')
      navegar('categorias')
    } catch (error) {
      setErroAuth(error.status === 409 ? 'Este e-mail já está cadastrado.'
        : error.status === 401 ? 'E-mail ou senha inválidos.' : error.message)
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
    if (usuario) navegar('categorias')
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
    setTela('resultado')
  }, [])

  function abrirRanking() {
    setRanking(carregarRanking())
    setTela('ranking')
  }

  async function iniciarQuiz(categoria) {
    if (enviandoRef.current) return

    enviandoRef.current = true
    setRequisicaoEmAndamento(true)
    setErro('')
    try {
      const novaPartida = await criarPartida(usuario ? undefined : jogador, categoria)
      setCategoriaSelecionada(novaPartida.categoria)
      setPartida(novaPartida)
      setPerguntaAtual(0)
      setTempoRestante(TEMPO_POR_PERGUNTA)
      setRespostaSelecionada(null)
      setResultadoResposta(null)
      timeoutEnviadoRef.current = false
      resultadoSalvoRef.current = false
      respostaConfirmadaRef.current = false
      setTela('jogando')
    } catch (error) {
      setErro(error.message)
      if (error.status === 401 || (usuario && error.status === 422 &&
        error.message === 'jogador é obrigatório para partidas como convidado')) {
        setUsuario(null)
        setStatusSessao('anonimo')
        setErro('Sua sessão não está disponível. Entre novamente para iniciar a partida.')
        setTela('login')
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
  }, [tempoRestante, tela, resultadoResposta, requisicaoEmAndamento, responder])

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
    <main>
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
        <TelaJogador confirmarJogador={(nome) => { setJogador(nome); setTela('categorias') }} />
      )}
      {tela === 'categorias' && (
        <TelaCategorias
          selecionarCategoria={iniciarQuiz}
          carregando={requisicaoEmAndamento}
        />
      )}
      {tela === 'jogando' && pergunta && (
        <TelaQuiz
          pergunta={pergunta}
          perguntaAtual={perguntaAtual}
          totalPerguntas={TOTAL_PERGUNTAS}
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
          categoriaSelecionada={categoriaSelecionada}
          iniciarQuiz={() => { setErro(''); setTela('categorias') }}
          verRanking={abrirRanking}
          voltarInicio={() => { setErro(''); setTela('inicio') }}
        />
      )}
      {tela === 'ranking' && (
        <TelaRanking
          ranking={ranking}
          voltarInicio={() => setTela('inicio')}
          trocarJogador={jogarAtual}
        />
      )}
    </main>
  )
}

export default App
