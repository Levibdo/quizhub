import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

import TelaJogador from './components/TelaJogador'
import TelaInicial from './components/TelaInicial'
import TelaCategorias from './components/TelaCategorias'
import TelaQuiz from './components/TelaQuiz'
import TelaResultado from './components/TelaResultado'
import TelaRanking from './components/TelaRanking'
import { criarPartida, enviarResposta } from './services/api'
import { carregarRanking, salvarResultado } from './utils/ranking'

const TEMPO_POR_PERGUNTA = 15
const TEMPO_FEEDBACK = 2000
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
  const timeoutEnviadoRef = useRef(false)
  const resultadoSalvoRef = useRef(false)

  const salvarEFinalizar = useCallback((estadoFinal) => {
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
      const novaPartida = await criarPartida(jogador, categoria)
      setCategoriaSelecionada(novaPartida.categoria)
      setPartida(novaPartida)
      setPerguntaAtual(0)
      setTempoRestante(TEMPO_POR_PERGUNTA)
      setRespostaSelecionada(null)
      setResultadoResposta(null)
      timeoutEnviadoRef.current = false
      resultadoSalvoRef.current = false
      setTela('jogando')
    } catch (error) {
      setErro(error.message)
    } finally {
      enviandoRef.current = false
      setRequisicaoEmAndamento(false)
    }
  }

  const responder = useCallback(async (indiceSelecionado, timeout = false) => {
    if (enviandoRef.current || resultadoResposta || !partida?.pergunta_atual) return

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

  useEffect(() => {
    if (!resultadoResposta) return

    const timerFeedback = setTimeout(() => {
      if (resultadoResposta.status === 'FINALIZADA') {
        salvarEFinalizar(resultadoResposta)
        return
      }
      setPartida(resultadoResposta)
      setPerguntaAtual((valorAtual) => valorAtual + 1)
      setTempoRestante(TEMPO_POR_PERGUNTA)
      setRespostaSelecionada(null)
      setResultadoResposta(null)
      timeoutEnviadoRef.current = false
      setErro('')
    }, TEMPO_FEEDBACK)
    return () => clearTimeout(timerFeedback)
  }, [resultadoResposta, salvarEFinalizar])

  const pergunta = partida?.pergunta_atual

  return (
    <main>
      {erro && <p className="mensagem-erro" role="alert">{erro}</p>}

      {tela === 'inicio' && (
        <TelaInicial
          escolherCategoria={() => { setErro(''); setTela('jogador') }}
          verRanking={abrirRanking}
        />
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
          trocarJogador={() => { setJogador(''); setTela('jogador') }}
        />
      )}
    </main>
  )
}

export default App
