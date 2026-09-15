import { useEffect, useState } from 'react'
import './App.css'

import { perguntas } from './data/perguntas'
import TelaInicial from './components/TelaInicial'
import TelaQuiz from './components/TelaQuiz'
import TelaResultado from './components/TelaResultado'

const TEMPO_POR_PERGUNTA = 15
const TEMPO_FEEDBACK = 1000

function App() {
  const [tela, setTela] = useState('inicio')
  const [perguntaAtual, setPerguntaAtual] = useState(0)
  const [pontuacao, setPontuacao] = useState(0)
  const [acertos, setAcertos] = useState(0)
  const [erros, setErros] = useState(0)

  const [tempoRestante, setTempoRestante] =
    useState(TEMPO_POR_PERGUNTA)

  const [respostaSelecionada, setRespostaSelecionada] =
    useState(null)

  const [respondido, setRespondido] = useState(false)

  const [pontosUltimaResposta, setPontosUltimaResposta] =
    useState(0)

  function iniciarQuiz() {
    setPerguntaAtual(0)
    setPontuacao(0)
    setAcertos(0)
    setErros(0)
    setTempoRestante(TEMPO_POR_PERGUNTA)
    setRespostaSelecionada(null)
    setRespondido(false)
    setPontosUltimaResposta(0)
    setTela('jogando')
  }

  function avancarPergunta() {
    const ultimaPergunta =
      perguntaAtual === perguntas.length - 1

    if (ultimaPergunta) {
      setTela('resultado')
    } else {
      setPerguntaAtual((valorAtual) => valorAtual + 1)
      setTempoRestante(TEMPO_POR_PERGUNTA)
      setRespostaSelecionada(null)
      setRespondido(false)
      setPontosUltimaResposta(0)
    }
  }

  function responder(indiceSelecionado) {
    if (respondido) {
      return
    }

    setRespondido(true)
    setRespostaSelecionada(indiceSelecionado)

    const pergunta = perguntas[perguntaAtual]

    if (indiceSelecionado === pergunta.correta) {
      const pontosGanhos =
        100 + tempoRestante * 10

      setAcertos((valorAtual) => valorAtual + 1)

      setPontuacao(
        (valorAtual) => valorAtual + pontosGanhos
      )

      setPontosUltimaResposta(pontosGanhos)
    } else {
      setErros((valorAtual) => valorAtual + 1)
      setPontosUltimaResposta(0)
    }

    setTimeout(() => {
      avancarPergunta()
    }, TEMPO_FEEDBACK)
  }

  // Controla apenas a contagem regressiva.
  useEffect(() => {
    if (tela !== 'jogando' || respondido) {
      return
    }

    const timer = setTimeout(() => {
      if (tempoRestante <= 1) {
        setTempoRestante(0)
        setRespondido(true)
        setErros((valorAtual) => valorAtual + 1)
        return
      }

      setTempoRestante(
        (valorAtual) => valorAtual - 1
      )
    }, 1000)

    return () => clearTimeout(timer)
  }, [tempoRestante, tela, respondido])

  // Depois que o tempo acaba, mantém o feedback
  // na tela por 1 segundo e então avança.
  useEffect(() => {
    if (
      tela !== 'jogando' ||
      !respondido ||
      tempoRestante !== 0
    ) {
      return
    }

    const timerFeedback = setTimeout(() => {
      const ultimaPergunta =
        perguntaAtual === perguntas.length - 1

      if (ultimaPergunta) {
        setTela('resultado')
      } else {
        setPerguntaAtual(
          (valorAtual) => valorAtual + 1
        )

        setTempoRestante(TEMPO_POR_PERGUNTA)
        setRespostaSelecionada(null)
        setRespondido(false)
        setPontosUltimaResposta(0)
      }
    }, TEMPO_FEEDBACK)

    return () => clearTimeout(timerFeedback)
  }, [
    tela,
    respondido,
    tempoRestante,
    perguntaAtual,
  ])

  const pergunta = perguntas[perguntaAtual]

  return (
    <main>
      {tela === 'inicio' && (
        <TelaInicial iniciarQuiz={iniciarQuiz} />
      )}

      {tela === 'jogando' && (
        <TelaQuiz
          pergunta={pergunta}
          perguntaAtual={perguntaAtual}
          totalPerguntas={perguntas.length}
          pontuacao={pontuacao}
          tempoRestante={tempoRestante}
          responder={responder}
          respostaSelecionada={respostaSelecionada}
          respondido={respondido}
          pontosUltimaResposta={pontosUltimaResposta}
        />
      )}

      {tela === 'resultado' && (
        <TelaResultado
          acertos={acertos}
          erros={erros}
          pontuacao={pontuacao}
          iniciarQuiz={iniciarQuiz}
        />
      )}
    </main>
  )
}

export default App