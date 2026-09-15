import { useEffect, useState } from 'react'
import './App.css'

import TelaJogador from './components/TelaJogador'
import { perguntas } from './data/perguntas'
import TelaInicial from './components/TelaInicial'
import TelaCategorias from './components/TelaCategorias'
import TelaQuiz from './components/TelaQuiz'
import TelaResultado from './components/TelaResultado'
import TelaRanking from './components/TelaRanking'

import {
  carregarRanking,
  salvarResultado,
} from './utils/ranking'


const TEMPO_POR_PERGUNTA = 15
const TEMPO_FEEDBACK = 1000
const PERGUNTAS_POR_PARTIDA = 3

function App() {
  const [tela, setTela] = useState('inicio')
  const [categoriaSelecionada, setCategoriaSelecionada] =
    useState(null)
  const [jogador, setJogador] = useState('')
  const [perguntaAtual, setPerguntaAtual] = useState(0)
  const [pontuacao, setPontuacao] = useState(0)
  const [acertos, setAcertos] = useState(0)
  const [erros, setErros] = useState(0)

  const [resultadoSalvo, setResultadoSalvo] =
    useState(false)
  const [tempoRestante, setTempoRestante] =
    useState(TEMPO_POR_PERGUNTA)

  const [respostaSelecionada, setRespostaSelecionada] =
    useState(null)

  const [respondido, setRespondido] = useState(false)

  const [pontosUltimaResposta, setPontosUltimaResposta] =
    useState(0)

  const [perguntasDoQuiz, setPerguntasDoQuiz] =
    useState([])
  const [ranking, setRanking] = useState(
    carregarRanking
  )
  function finalizarQuiz(
    pontuacaoFinal,
    acertosFinais,
    errosFinais
  ) {
    if (!resultadoSalvo) {
      const resultado = {
        id: Date.now(),
        jogador,
        categoria: categoriaSelecionada,
        pontuacao: pontuacaoFinal,
        acertos: acertosFinais,
        erros: errosFinais,
      }

      salvarResultado(resultado)
      setRanking(carregarRanking())
      setResultadoSalvo(true)
    }

    setTela('resultado')
  }
  function abrirRanking() {
    setRanking(carregarRanking())
    setTela('ranking')
  }
  function identificarJogador() {
    setTela('jogador')
  }

  function confirmarJogador(nome) {
    setJogador(nome)
    setTela('categorias')
  }

  function escolherCategoria() {
    setTela('categorias')
  }

  function embaralharPerguntas(lista) {
    return [...lista].sort(() => Math.random() - 0.5)
  }

  function iniciarQuiz(categoria) {
    const perguntasDaCategoria = perguntas.filter(
      (pergunta) => pergunta.categoria === categoria
    )

    const perguntasSorteadas =
      embaralharPerguntas(perguntasDaCategoria)

    const perguntasDaPartida =
      perguntasSorteadas.slice(
        0,
        PERGUNTAS_POR_PARTIDA
      )

    setCategoriaSelecionada(categoria)
    setPerguntasDoQuiz(perguntasDaPartida)
    setResultadoSalvo(false)
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
    setPerguntaAtual((valorAtual) => valorAtual + 1)
    setTempoRestante(TEMPO_POR_PERGUNTA)
    setRespostaSelecionada(null)
    setRespondido(false)
    setPontosUltimaResposta(0)
  }
  function responder(indiceSelecionado) {
    if (respondido) {
      return
    }

    setRespondido(true)
    setRespostaSelecionada(indiceSelecionado)

    const pergunta = perguntasDoQuiz[perguntaAtual]

    const respostaCorreta =
      indiceSelecionado === pergunta.correta

    const ultimaPergunta =
      perguntaAtual === perguntasDoQuiz.length - 1

    let novaPontuacao = pontuacao
    let novosAcertos = acertos
    let novosErros = erros

    if (respostaCorreta) {
      const pontosGanhos =
        100 + tempoRestante * 10

      novaPontuacao = pontuacao + pontosGanhos
      novosAcertos = acertos + 1

      setPontuacao(novaPontuacao)
      setAcertos(novosAcertos)
      setPontosUltimaResposta(pontosGanhos)
    } else {
      novosErros = erros + 1

      setErros(novosErros)
      setPontosUltimaResposta(0)
    }

    setTimeout(() => {
      if (ultimaPergunta) {
        finalizarQuiz(
          novaPontuacao,
          novosAcertos,
          novosErros
        )
      } else {
        avancarPergunta()
      }
    }, TEMPO_FEEDBACK)
  }
  function trocarJogador() {
    setJogador('')
    setTela('jogador')
  }

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
        perguntaAtual === perguntasDoQuiz.length - 1

      if (ultimaPergunta) {
        if (!resultadoSalvo) {
          const resultado = {
            id: Date.now(),
            jogador,
            categoria: categoriaSelecionada,
            pontuacao,
            acertos,
            erros,
          }

          salvarResultado(resultado)
          setRanking(carregarRanking())
          setResultadoSalvo(true)
        }

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
    perguntasDoQuiz.length,
    resultadoSalvo,
    jogador,
    categoriaSelecionada,
    pontuacao,
    acertos,
    erros,
  ])

  const pergunta = perguntasDoQuiz[perguntaAtual]

  return (
    <main>
      {tela === 'inicio' && (
        <TelaInicial
          escolherCategoria={identificarJogador}
        />
      )}

      {tela === 'jogador' && (
        <TelaJogador
          confirmarJogador={confirmarJogador}
        />
      )}

      {tela === 'categorias' && (
        <TelaCategorias
          selecionarCategoria={iniciarQuiz}
        />
      )}

      {tela === 'jogando' && pergunta && (
        <TelaQuiz
          pergunta={pergunta}
          perguntaAtual={perguntaAtual}
          totalPerguntas={perguntasDoQuiz.length}
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
          jogador={jogador}
          acertos={acertos}
          erros={erros}
          pontuacao={pontuacao}
          categoriaSelecionada={categoriaSelecionada}
          iniciarQuiz={escolherCategoria}
          verRanking={abrirRanking}

        />
      )}
      {tela === 'ranking' && (
        <TelaRanking
          ranking={ranking}
          escolherCategoria={escolherCategoria}
          trocarJogador={trocarJogador}
        />
      )}
    </main>
  )
}

export default App