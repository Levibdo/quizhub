import { useCallback, useEffect, useRef, useState } from 'react'
import {
  abandonarSalaNemAPato,
  carregarSessaoNemAPato,
  criarSalaNemAPato,
  desafiarPalpiteNemAPato,
  entrarSalaNemAPato,
  enviarPalpiteNemAPato,
  iniciarPartidaNemAPato,
  jogarNovamenteNemAPato,
  iniciarProximaRodadaNemAPato,
  iniciarRodadaNemAPato,
  recuperarSalaNemAPato,
  removerSessaoNemAPato,
  salvarSessaoNemAPato,
} from '../services/nemAPato'

const INTERVALO_LOBBY_MS = 1000

function novoClientActionId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (caractere) => {
    const aleatorio = Math.floor(Math.random() * 16)
    const valor = caractere === 'x' ? aleatorio : (aleatorio & 0x3) | 0x8
    return valor.toString(16)
  })
}

function segundosAteDeadline(terminaEm, agora = Date.now()) {
  if (!terminaEm) return 0
  return Math.max(0, Math.ceil((new Date(terminaEm).getTime() - agora) / 1000))
}

function formatarTempo(segundos) {
  const minutos = Math.floor(segundos / 60)
  return minutos + ":" + String(segundos % 60).padStart(2, "0")
}

function formatarPalpite(valor, unidade) {
  if (valor === null || valor === undefined) return '—'
  const numero = new Intl.NumberFormat('pt-BR').format(valor)
  return unidade ? `${numero} ${unidade}` : numero
}

function ordenarPlacarFinal(jogadores) {
  return [...jogadores]
    .filter((jogador) => jogador.status === 'ATIVO')
    .sort((a, b) => a.patos - b.patos || a.ordem_circular - b.ordem_circular)
}

function possuiEstadoTerminalCompleto(estado) {
  const partida = estado?.partida
  return partida?.status === 'CANCELADA'
    || (partida?.status === 'FINALIZADA' && Boolean(partida.resultado_final))
}

function mensagemErro(error, acao = 'operacao') {
  if (error.message === 'sala inexistente') return 'Sala não encontrada.'
  if (error.message === 'sala cheia') return 'A sala está cheia.'
  if (error.message === 'nome já está em uso na sala') return 'Este nome já está sendo usado.'
  if (error.message === 'sala não está aguardando') return 'Não é mais possível entrar nesta sala.'
  if (error.message === 'credencial Nem a Pato inválida' || error.message === 'credencial Nem a Pato ausente') {
    return 'Sua participação não está mais disponível. Entre na sala novamente.'
  }
  if (error.message === 'participante não está ativo') return 'Sua participação foi encerrada.'
  if (error.message.includes('pelo menos 3 participantes')) return 'São necessários pelo menos 3 jogadores para iniciar.'
  if (error.message.includes('10 perguntas Nem a Pato')) return 'Ainda não há 10 perguntas numéricas ativas para iniciar uma partida.'
  if (error.message === 'somente o anfitrião pode iniciar a rodada') return 'Somente o anfitrião pode iniciar a rodada.'
  if (error.message.includes('somente o anfitrião')) return 'Somente o anfitrião pode iniciar a partida.'
  if (error.message === 'não é sua vez') return 'Não é sua vez.'
  if (error.message?.startsWith('seu palpite precisa ser maior que ')) {
    return `Seu palpite precisa ser maior que ${error.message.split('maior que ')[1]}.`
  }
  if (error.message === 'rodada já iniciada') return 'A rodada já começou.'
  if (error.message === 'sala não está em partida') return 'A rodada ainda não começou.'
  if (error.message === 'esta rodada não aceita mais palpites') return 'Esta rodada não aceita mais palpites.'
  if (error.message === 'sua participação não está mais ativa') return 'Sua participação não está mais ativa.'
  if (error.message === 'sala já possui uma partida em andamento') return 'Esta sala já tem uma partida em andamento.'
  if (error.message === 'rodada já foi resolvida') return 'Esta rodada já foi resolvida. Sincronizando o resultado.'
  if (error.message === 'palpite já foi desafiado') return 'Este palpite já foi desafiado. Sincronizando o resultado.'
  if (error.status === 422) return error.message || 'Confira os dados informados.'
  if (error.message === 'Não foi possível conectar ao servidor.') return error.message
  return acao === 'recuperar'
    ? 'Não foi possível recuperar esta sala. Verifique sua conexão e tente novamente.'
    : 'Não foi possível concluir a operação. Tente novamente.'
}

function rotaAtual() {
  const caminho = window.location.pathname
  const encontrado = caminho.match(/^\/nem-a-pato(?:\/sala\/([^/]+))?\/?$/)
  if (!encontrado) return { tipo: 'fora' }
  return encontrado[1]
    ? { tipo: 'lobby', codigo: decodeURIComponent(encontrado[1]).toUpperCase() }
    : { tipo: 'inicio' }
}

function TelaNemAPato({ voltarInicio, registrarAcaoMarca }) {
  const [rota, setRota] = useState(() => rotaAtual())
  const [formulario, setFormulario] = useState(null)
  const [nome, setNome] = useState('')
  const [codigo, setCodigo] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [palpite, setPalpite] = useState('')
  const [segundosRestantes, setSegundosRestantes] = useState(0)
  const [confirmacaoDesafio, setConfirmacaoDesafio] = useState(false)
  const [modalSaida, setModalSaida] = useState(null)
  const [sessao, setSessao] = useState(() => {
    const inicial = rotaAtual()
    return inicial.tipo === 'lobby' ? carregarSessaoNemAPato(inicial.codigo) : null
  })
  const [estadoSala, setEstadoSala] = useState(null)
  const [podeSincronizar, setPodeSincronizar] = useState(false)
  const estadoTerminalCompleto = possuiEstadoTerminalCompleto(estadoSala)
  const estadoSemRevanche = estadoSala?.partida?.status === 'CANCELADA'
  const operacaoRef = useRef(false)
  const acaoPalpiteRef = useRef(null)
  const acaoDesafioRef = useRef(null)
  const recuperacaoInicial = useRef(false)
  const botaoCancelarDesafioRef = useRef(null)
  const botaoCancelarSaidaRef = useRef(null)

  const navegar = useCallback((destino) => {
    const caminho = destino.tipo === 'lobby'
      ? `/nem-a-pato/sala/${encodeURIComponent(destino.codigo)}`
      : '/nem-a-pato'
    window.history.pushState({}, '', caminho)
    setRota(destino)
    setErro('')
    setSucesso('')
  }, [])

  useEffect(() => {
    function aoNavegar() {
      const atual = rotaAtual()
      if (atual.tipo === 'fora') {
        voltarInicio()
        return
      }
      setRota(atual)
      setSessao(atual.tipo === 'lobby' ? carregarSessaoNemAPato(atual.codigo) : null)
      setEstadoSala(null)
      setPodeSincronizar(false)
      recuperacaoInicial.current = false
      setErro('')
      setSucesso('')
    }
    window.addEventListener('popstate', aoNavegar)
    return () => window.removeEventListener('popstate', aoNavegar)
  }, [voltarInicio])

  const atualizarEstado = useCallback(async (credencial, silencioso = false, estaMontado = () => true) => {
    try {
      const atual = await recuperarSalaNemAPato(credencial.codigo, credencial.token)
      if (!estaMontado()) return false
      setEstadoSala(atual)
      setPodeSincronizar(true)
      setErro((valor) => valor === 'Sua participação não está mais disponível. Entre na sala novamente.' ? '' : valor)
      recuperacaoInicial.current = true
      return true
    } catch (error) {
      if (!estaMontado()) return false
      if (error.status === 401 || error.status === 403 || error.status === 404) {
        removerSessaoNemAPato(credencial.codigo)
        setSessao(null)
        setEstadoSala(null)
        setPodeSincronizar(false)
        setErro(mensagemErro(error, 'recuperar'))
        recuperacaoInicial.current = true
        return false
      }
      if (!silencioso) setErro(mensagemErro(error, 'recuperar'))
      return false
    }
  }, [])

  useEffect(() => {
    if (rota.tipo !== 'lobby' || !sessao || sessao.codigo !== rota.codigo || recuperacaoInicial.current) return undefined
    let montado = true
    let requisicaoEmCurso = false
    const recuperar = async () => {
      if (requisicaoEmCurso || !montado) return
      requisicaoEmCurso = true
      await atualizarEstado(sessao, false, () => montado)
      requisicaoEmCurso = false
    }
    recuperar()
    return () => { montado = false }
  }, [rota, sessao, atualizarEstado])

  useEffect(() => {
    if (
      rota.tipo !== 'lobby'
      || !sessao
      || !podeSincronizar
      || estadoSemRevanche
    ) return undefined
    let montado = true
    let requisicaoEmCurso = false
    const intervalo = window.setInterval(async () => {
      if (!montado || requisicaoEmCurso) return
      requisicaoEmCurso = true
      await atualizarEstado(sessao, true, () => montado)
      requisicaoEmCurso = false
    }, INTERVALO_LOBBY_MS)
    return () => {
      montado = false
      window.clearInterval(intervalo)
    }
  }, [rota, sessao, podeSincronizar, atualizarEstado, estadoSemRevanche])

  useEffect(() => {
    const terminaEm = estadoSala?.partida?.rodada?.termina_em
    const emAndamento = estadoSala?.partida?.rodada?.status === "EM_ANDAMENTO"
    if (!emAndamento || !terminaEm) return undefined
    const atualizar = () => setSegundosRestantes(segundosAteDeadline(terminaEm))
    const inicio = globalThis.setTimeout(atualizar, 0)
    const intervalo = window.setInterval(atualizar, 1000)
    return () => {
      globalThis.clearTimeout(inicio)
      window.clearInterval(intervalo)
    }
  }, [estadoSala?.partida?.rodada?.id, estadoSala?.partida?.rodada?.status, estadoSala?.partida?.rodada?.termina_em])

  useEffect(() => {
    if (!confirmacaoDesafio) return undefined
    botaoCancelarDesafioRef.current?.focus()
    const fecharComEscape = (event) => {
      if (event.key === 'Escape' && !carregando) setConfirmacaoDesafio(false)
    }
    window.addEventListener('keydown', fecharComEscape)
    return () => window.removeEventListener('keydown', fecharComEscape)
  }, [confirmacaoDesafio, carregando])

  useEffect(() => {
    if (!modalSaida) return undefined
    botaoCancelarSaidaRef.current?.focus()
    const fecharComEscape = (event) => {
      if (event.key === 'Escape' && !carregando) setModalSaida(null)
    }
    window.addEventListener('keydown', fecharComEscape)
    return () => window.removeEventListener('keydown', fecharComEscape)
  }, [modalSaida, carregando])

  async function iniciarParticipacao(acao) {
    if (operacaoRef.current) return
    operacaoRef.current = true
    setCarregando(true)
    setErro('')
    setSucesso('')
    const nomeLimpo = nome.trim()
    const codigoLimpo = codigo.trim().toUpperCase()
    try {
      const criada = acao === 'criar'
        ? await criarSalaNemAPato(nomeLimpo)
        : await entrarSalaNemAPato(codigoLimpo, nomeLimpo)
      const codigoSala = criada.sala.codigo.toUpperCase()
      salvarSessaoNemAPato(codigoSala, criada.credencial_participante)
      recuperacaoInicial.current = true
      setSessao({ codigo: codigoSala, token: criada.credencial_participante })
      setEstadoSala(criada)
      setPodeSincronizar(true)
      setFormulario(null)
      setNome('')
      setCodigo('')
      navegar({ tipo: 'lobby', codigo: codigoSala })
    } catch (error) {
      setErro(mensagemErro(error, acao))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }

  async function tentarRecuperarSala() {
    if (operacaoRef.current || !sessao) return
    operacaoRef.current = true
    setCarregando(true)
    const recuperou = await atualizarEstado(sessao, false)
    if (recuperou) setErro('')
    operacaoRef.current = false
    setCarregando(false)
  }

  function limparParticipacaoLocal(destino = 'modo') {
    if (sessao) removerSessaoNemAPato(sessao.codigo)
    setSessao(null)
    setEstadoSala(null)
    setPodeSincronizar(false)
    recuperacaoInicial.current = false
    setModalSaida(null)
    if (destino === 'home') voltarInicio()
    else navegar({ tipo: 'inicio' })
  }

  const solicitarSaida = useCallback((destino = 'modo') => {
    const partida = estadoSala?.partida
    if (
      partida?.status === 'FINALIZADA'
      || partida?.status === 'CANCELADA'
    ) {
      if (sessao) removerSessaoNemAPato(sessao.codigo)
      setSessao(null)
      setEstadoSala(null)
      setPodeSincronizar(false)
      recuperacaoInicial.current = false
      voltarInicio()
      return
    }
    if (partida?.rodada?.status === 'EM_ANDAMENTO') {
      setModalSaida({ tipo: 'bloqueio', destino })
      return
    }
    if (sessao && estadoSala?.participante?.status === 'ATIVO') {
      setErro('')
      setModalSaida({ tipo: 'confirmacao', destino })
      return
    }
    voltarInicio()
  }, [estadoSala, sessao, voltarInicio])

  useEffect(() => {
    if (!registrarAcaoMarca) return undefined
    registrarAcaoMarca(() => solicitarSaida('home'))
    return () => registrarAcaoMarca(null)
  }, [registrarAcaoMarca, solicitarSaida])

  async function sairDaSala() {
    if (operacaoRef.current || !sessao) return
    operacaoRef.current = true
    setCarregando(true)
    setErro('')
    try {
      await abandonarSalaNemAPato(sessao.codigo, sessao.token)
      const destino = modalSaida?.destino || 'modo'
      limparParticipacaoLocal(destino)
    } catch (error) {
      setErro(mensagemErro(error, 'abandonar'))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }

  async function iniciarPartida() {
    if (operacaoRef.current || !sessao) return
    operacaoRef.current = true
    setCarregando(true)
    setErro('')
    try {
      const atual = await iniciarPartidaNemAPato(sessao.codigo, sessao.token)
      setEstadoSala(atual)
      setPodeSincronizar(true)
    } catch (error) {
      setErro(mensagemErro(error, 'iniciar'))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }

  async function iniciarRodada() {
    if (operacaoRef.current || !sessao) return
    operacaoRef.current = true
    setCarregando(true)
    setErro('')
    try {
      const atual = await iniciarRodadaNemAPato(sessao.codigo, sessao.token)
      setEstadoSala(atual)
    } catch (error) {
      setErro(mensagemErro(error, 'iniciar-rodada'))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }

  async function confirmarPalpite(event) {
    event.preventDefault()
    const rodada = estadoSala?.partida?.rodada
    if (operacaoRef.current || !sessao || !rodada) return
    if (!/^\d+$/.test(palpite)) {
      setErro('Informe um número inteiro maior ou igual a zero.')
      return
    }
    const valor = Number(palpite)
    if (!Number.isSafeInteger(valor) || valor < 0) {
      setErro('Informe um número inteiro válido.')
      return
    }
    if (!acaoPalpiteRef.current || acaoPalpiteRef.current.valor !== valor) {
      acaoPalpiteRef.current = { valor, id: novoClientActionId() }
    }
    operacaoRef.current = true
    setCarregando(true)
    setErro('')
    try {
      const atual = await enviarPalpiteNemAPato(
        sessao.codigo,
        rodada.id,
        sessao.token,
        valor,
        acaoPalpiteRef.current.id,
      )
      setEstadoSala(atual)
      setPalpite('')
      acaoPalpiteRef.current = null
    } catch (error) {
      setErro(mensagemErro(error, 'palpite'))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }


  function abrirConfirmacaoDesafio() {
    if (!operacaoRef.current) setConfirmacaoDesafio(true)
  }

  async function confirmarDesafio() {
    const rodada = estadoSala?.partida?.rodada
    const ultimo = rodada?.palpites?.at(-1)
    if (operacaoRef.current || !sessao || !rodada || !ultimo) return
    if (!acaoDesafioRef.current || acaoDesafioRef.current.rodadaId !== rodada.id) {
      acaoDesafioRef.current = { rodadaId: rodada.id, id: novoClientActionId() }
    }
    operacaoRef.current = true
    setCarregando(true)
    setErro("")
    try {
      const atual = await desafiarPalpiteNemAPato(
        sessao.codigo,
        rodada.id,
        sessao.token,
        acaoDesafioRef.current.id,
      )
      setEstadoSala(atual)
      acaoDesafioRef.current = null
      setConfirmacaoDesafio(false)
    } catch (error) {
      setErro(mensagemErro(error, "desafio"))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }


  async function iniciarProximaRodada() {
    const rodada = estadoSala?.partida?.rodada
    if (operacaoRef.current || !sessao || !rodada) return
    operacaoRef.current = true
    setCarregando(true)
    setErro("")
    try {
      const atual = await iniciarProximaRodadaNemAPato(
        sessao.codigo,
        rodada.id,
        sessao.token,
      )
      setEstadoSala(atual)
      setPalpite("")
      acaoPalpiteRef.current = null
      acaoDesafioRef.current = null
    } catch (error) {
      setErro(mensagemErro(error, "proxima-rodada"))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }

  async function jogarNovamente() {
    if (operacaoRef.current || !sessao) return
    operacaoRef.current = true
    setCarregando(true)
    setErro('')
    try {
      const atual = await jogarNovamenteNemAPato(sessao.codigo, sessao.token)
      setEstadoSala(atual)
      setPalpite('')
      acaoPalpiteRef.current = null
      acaoDesafioRef.current = null
    } catch (error) {
      setErro(mensagemErro(error, 'revanche'))
    } finally {
      operacaoRef.current = false
      setCarregando(false)
    }
  }

  function copiarCodigo() {
    const escrita = navigator.clipboard?.writeText(rota.codigo)
    if (!escrita) {
      setSucesso('Código da sala: ' + rota.codigo)
      return
    }
    escrita.then(() => setSucesso('Código copiado.'))
      .catch(() => setSucesso('Código da sala: ' + rota.codigo))
  }

  if (rota.tipo === 'lobby') {
    const sala = estadoSala?.sala?.codigo?.toUpperCase() === rota.codigo
      ? estadoSala.sala
      : null
    const participantes = sala?.participantes || []
    const eu = estadoSala?.participante
    const partida = estadoSala?.partida
    const rodada = partida?.rodada
    const prazoEsgotado = rodada?.status === 'EM_ANDAMENTO'
      && Boolean(rodada.termina_em)
      && segundosAteDeadline(rodada.termina_em) === 0
    const tempoExibido = rodada?.status === 'EM_ANDAMENTO'
      && segundosRestantes === 0
      && !prazoEsgotado
      ? segundosAteDeadline(rodada.termina_em)
      : segundosRestantes
    const ultimoPalpite = rodada?.palpites?.at(-1)
    const jogadorAtual = partida?.jogadores?.find((jogador) => jogador.eh_eu)
    const podeDesafiar = rodada?.status === 'EM_ANDAMENTO'
      && !prazoEsgotado
      && ultimoPalpite
      && !ultimoPalpite.jogador.eh_eu
      && jogadorAtual?.status === 'ATIVO'
    const podeAbandonar = eu?.status === 'ATIVO' && (
      sala?.status === 'AGUARDANDO'
      || (
        sala?.status === 'EM_PARTIDA'
        && partida?.status === 'EM_ANDAMENTO'
        && (
          partida.rodada_atual === 0
          || rodada?.status === 'RESULTADO'
        )
      )
    )
    const mensagemSemSessao = !sessao && !erro
      ? 'Não há uma participação salva para esta sala neste navegador.'
      : erro
    const resultadoFinal = partida?.resultado_final
    const placarFinal = ordenarPlacarFinal(partida?.jogadores || [])
    const voltarAoInicio = () => limparParticipacaoLocal('home')
    return (
      <section className="np-screen" aria-labelledby="np-title" aria-busy={carregando}>
        <header className="np-heading">
          <span className="np-eyebrow">QuizHub // Sala multiplayer</span>
          <h1 id="np-title">NEM A PATO!</h1>
          <p>{sala?.status === 'EM_PARTIDA' ? 'Partida em andamento' : 'Lobby da sala'}</p>
        </header>
        {podeAbandonar && (
          <button className="np-exit-room" type="button" disabled={carregando} onClick={() => solicitarSaida('modo')}>
            SAIR DA SALA
          </button>
        )}
        {mensagemSemSessao && <p className="np-message np-message--error" role="alert">{mensagemSemSessao}</p>}
        {sucesso && <p className="np-message" role="status">{sucesso}</p>}
        {!sala && sessao && !erro && <p className="np-sync" role="status">Recuperando sua participação...</p>}
        {!sala && sessao && erro && (
          <button className="button-secondary np-retry" type="button" disabled={carregando} onClick={tentarRecuperarSala}>
            {carregando ? 'Reconectando...' : 'Tentar novamente'}
          </button>
        )}
        {!sessao && (
          <button className="button-secondary" type="button" onClick={() => navegar({ tipo: 'inicio' })}>
            Voltar para Nem a Pato
          </button>
        )}
        {sala && (
          <>
            {sala.status === 'ENCERRADA' && !estadoTerminalCompleto && (
              <p role="status">Sincronizando resultado final...</p>
            )}
            {estadoTerminalCompleto && partida && (
              <section className="np-final" aria-labelledby="np-final-title">
                <p className="np-final__eyebrow">Nem a Pato!</p>
                <h2 id="np-final-title">
                  {partida.status === 'CANCELADA' ? 'PARTIDA CANCELADA' : 'FIM DE JOGO'}
                </h2>
                {partida.status === 'CANCELADA' ? (
                  <p>Não há jogadores ativos suficientes para continuar.</p>
                ) : resultadoFinal?.empate_geral ? (
                  <section className="np-final__highlight">
                    <h3>EMPATE GERAL</h3>
                    <p>Todo mundo venceu. Todo mundo também virou Pato da Partida.</p>
                  </section>
                ) : (
                  <div className="np-final__extremes">
                    <section>
                      <h3>{resultadoFinal?.vencedores.length > 1 ? 'VENCEDORES' : 'VENCEDOR'}</h3>
                      <strong>{resultadoFinal?.vencedores.map((j) => j.nome).join(' • ')}</strong>
                      <span>{resultadoFinal?.vencedores[0]?.patos} patos</span>
                    </section>
                    <section>
                      <h3>{resultadoFinal?.patos_da_partida.length > 1 ? 'PATOS DA PARTIDA' : 'PATO DA PARTIDA'}</h3>
                      <strong>{resultadoFinal?.patos_da_partida.map((j) => j.nome).join(' • ')}</strong>
                      <span>{resultadoFinal?.patos_da_partida[0]?.patos} patos</span>
                    </section>
                  </div>
                )}
                <section className="np-final__score" aria-label="Placar final">
                  <h3>PLACAR FINAL</h3>
                  <ol>
                    {placarFinal.map((jogador) => (
                      <li key={jogador.id}>
                        <span>{jogador.nome}</span><strong>{jogador.patos} 🦆</strong>
                      </li>
                    ))}
                  </ol>
                </section>
                {resultadoFinal?.abandonados.length > 0 && (
                  <section className="np-final__abandoned">
                    <h3>ABANDONARAM</h3>
                    {resultadoFinal.abandonados.map((jogador) => (
                      <p key={jogador.id}>{jogador.nome} — {jogador.patos} patos</p>
                    ))}
                  </section>
                )}
                {partida.status === 'FINALIZADA' && eu?.eh_anfitriao && sala.participantes_ativos >= 3 && (
                  <button className="np-start-button" type="button" disabled={carregando} onClick={jogarNovamente}>
                    {carregando ? 'Preparando revanche...' : 'JOGAR NOVAMENTE'}
                  </button>
                )}
                {partida.status === 'FINALIZADA' && !eu?.eh_anfitriao && (
                  <p role="status">Esperando o host decidir se haverá revanche...</p>
                )}
                <button className="np-start-button" type="button" onClick={voltarAoInicio}>
                  VOLTAR AO INÍCIO
                </button>
              </section>
            )}
            {sala.status === 'EM_PARTIDA' && (
              <section className="np-started" aria-labelledby="np-started-title">
                <p className="np-started__eyebrow">Sala {sala.codigo}</p>
                <h2 id="np-started-title">A PARTIDA COMEÇOU</h2>
                {partida ? (
                  <>
                    {partida.numero > 1 && <p className="np-started__eyebrow">REVANCHE</p>}
                    <p>Partida {partida.numero} · {partida.total_rodadas} rodadas · {Math.floor(partida.duracao_rodada_segundos / 60)} minutos por rodada</p>
                    <section className="np-score" aria-label="Placar de patos">
                      <h3>PATOS</h3>
                      <ul>
                        {partida.jogadores.map((jogador) => (
                          <li key={jogador.id}>
                            <span>{jogador.nome}</span>
                            <strong>{jogador.patos ?? 0} 🦆{jogador.eh_eu && <small>Você</small>}</strong>
                          </li>
                        ))}
                      </ul>
                    </section>
                  </>
                ) : <p role="status">Recuperando a partida...</p>}
                {rodada?.status === 'AGUARDANDO_INICIO' && (
                  eu?.eh_anfitriao ? (
                    <button className="np-start-button" type="button" disabled={carregando} onClick={iniciarRodada}>
                      {carregando ? 'Iniciando rodada...' : 'Iniciar rodada'}
                    </button>
                  ) : <p role="status">Aguardando o anfitrião iniciar a rodada...</p>
                )}
                {rodada?.status === 'EM_ANDAMENTO' && (
                  <section className="np-round" aria-labelledby="np-round-title">
                    <header className="np-round__header">
                      <p className="np-round__counter">Rodada {rodada.numero} de {partida.total_rodadas}</p>
                      <p className={tempoExibido <= 10 ? "np-timer np-timer--urgent" : "np-timer"} aria-label={`${tempoExibido} segundos restantes`}>
                        <span>Tempo</span><strong>{formatarTempo(tempoExibido)}</strong>
                      </p>
                    </header>
                    <h3 id="np-round-title" className="np-visually-hidden">Pergunta</h3>
                    <p className="np-round__question">{rodada.pergunta?.enunciado}</p>
                    {rodada.pergunta?.unidade && <p className="np-round__unit">Responda em <strong>{rodada.pergunta.unidade}</strong></p>}
                    <div className="np-round__status">
                      <p>Maior palpite <strong>{formatarPalpite(rodada.maior_palpite, rodada.pergunta?.unidade)}</strong></p>
                      <p className={rodada.jogador_da_vez?.eh_eu ? 'np-turn np-turn--you' : 'np-turn'}>
                        <span className="np-visually-hidden">Jogador da vez: </span>
                        {rodada.jogador_da_vez?.eh_eu ? 'Sua vez' : 'Vez de'}
                        <strong>{rodada.jogador_da_vez?.eh_eu ? 'Faça seu palpite' : rodada.jogador_da_vez?.nome}</strong>
                      </p>
                    </div>
                    {prazoEsgotado && <p className="np-sync" role="status">TEMPO ESGOTADO — confirmando resultado...</p>}
                    {rodada.palpites.length > 0 && (
                      <ol className="np-guess-history" aria-label="Histórico de palpites">
                        {rodada.palpites.map((item, indice) => (
                          <li className={indice === rodada.palpites.length - 1 ? 'np-guess-history__latest' : ''} key={item.ordem}>
                            <span>{item.jogador.nome}</span>
                            <strong>{formatarPalpite(item.valor, rodada.pergunta?.unidade)}</strong>
                          </li>
                        ))}
                      </ol>
                    )}
                    {rodada.jogador_da_vez?.eh_eu && !prazoEsgotado ? (
                      <form className="np-guess-form" onSubmit={confirmarPalpite}>
                        <label htmlFor="np-guess">Seu palpite</label>
                        {rodada.maior_palpite !== null && rodada.maior_palpite !== undefined && (
                          <p id="np-guess-hint">Seu palpite deve ser maior que {formatarPalpite(rodada.maior_palpite, rodada.pergunta?.unidade)}.</p>
                        )}
                        <input
                          id="np-guess"
                          type="number"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          min="0"
                          step="1"
                          aria-describedby={rodada.maior_palpite !== null && rodada.maior_palpite !== undefined ? 'np-guess-hint' : undefined}
                          value={palpite}
                          onChange={(event) => {
                            setPalpite(event.target.value.replace(/\D/g, ''))
                            acaoPalpiteRef.current = null
                          }}
                          disabled={carregando || prazoEsgotado}
                          required
                        />
                        <button type="submit" disabled={carregando || !palpite}>
                          {carregando ? 'Enviando...' : 'Confirmar palpite'}
                        </button>
                      </form>
                    ) : !prazoEsgotado ? (
                      <p role="status">Aguardando o palpite de {rodada.jogador_da_vez?.nome}...</p>
                    ) : null}
                    {podeDesafiar && (
                      <button
                        className="np-challenge"
                        type="button"
                        disabled={carregando}
                        onClick={abrirConfirmacaoDesafio}
                      >
                        {carregando ? "Desafiando..." : "NEM A PATO!"}
                      </button>
                    )}
                    {confirmacaoDesafio && ultimoPalpite && (
                      <div className="np-dialog-backdrop" role="presentation">
                        <section className="np-dialog" role="dialog" aria-modal="true" aria-labelledby="np-challenge-title" aria-describedby="np-challenge-description">
                          <p className="np-eyebrow">Confirme o desafio</p>
                          <h4 id="np-challenge-title">NEM A PATO!</h4>
                          <p id="np-challenge-description">Você quer desafiar o palpite de <strong>{ultimoPalpite.jogador.nome}: {formatarPalpite(ultimoPalpite.valor, rodada.pergunta?.unidade)}</strong>?</p>
                          <div className="np-dialog__actions">
                            <button type="button" className="np-challenge" disabled={carregando} onClick={confirmarDesafio}>
                              {carregando ? 'Confirmando desafio...' : 'CONFIRMAR DESAFIO'}
                            </button>
                            <button ref={botaoCancelarDesafioRef} type="button" className="button-secondary" disabled={carregando} onClick={() => setConfirmacaoDesafio(false)}>
                              CANCELAR
                            </button>
                          </div>
                        </section>
                      </div>
                    )}
                  </section>
                )}
                {rodada?.status === "RESULTADO" && (
                  <section className="np-round np-result" aria-labelledby="np-result-title">
                    <p className="np-round__counter">Rodada {rodada.numero} de {partida.total_rodadas}</p>
                    <h3 id="np-result-title">RESULTADO</h3>
                    <p className="np-round__question">{rodada.pergunta?.enunciado}</p>
                    <div className="np-result__answer">
                      <span>Resposta correta</span>
                      <strong>{formatarPalpite(rodada.pergunta?.resposta_numerica, rodada.pergunta?.unidade)}</strong>
                    </div>
                    {rodada.resultado_desafio && (
                      <>
                        <p>Último palpite: <strong>{rodada.resultado_desafio.palpite_desafiado.jogador.nome} — {formatarPalpite(rodada.resultado_desafio.palpite_desafiado.valor, rodada.pergunta?.unidade)}</strong></p>
                        <p><strong>{rodada.resultado_desafio.desafiante.nome}</strong> disse “Nem a Pato!”</p>
                        <p className="np-result__penalty"><strong>{rodada.resultado_desafio.jogador_penalizado.nome}</strong> recebeu 1 pato.</p>
                      </>
                    )}
                    {rodada.resultado_timeout && (
                      <>
                        <h4>TEMPO ESGOTADO</h4>
                        {rodada.resultado_timeout.ultimo_palpite ? (
                          <>
                            <p>Maior palpite: <strong>{rodada.resultado_timeout.autor_protegido.nome} — {formatarPalpite(rodada.resultado_timeout.ultimo_palpite.valor, rodada.pergunta?.unidade)}</strong></p>
                            <p><strong>{rodada.resultado_timeout.autor_protegido.nome}</strong> não recebeu pato. Os demais jogadores ativos receberam 1 pato.</p>
                          </>
                        ) : (
                          <>
                            <p>Ninguém enviou um palpite.</p>
                            <p>Nenhum pato foi aplicado.</p>
                          </>
                        )}
                      </>
                    )}
                    <p className="np-result__explanation">{rodada.pergunta?.explicacao}</p>
                    {rodada.numero < partida.total_rodadas ? (
                      jogadorAtual?.status === 'ATIVO' ? (
                        <>
                          <p className="np-hint">Qualquer jogador pode iniciar a próxima rodada.</p>
                        <button
                          className="np-start-button"
                          type="button"
                          disabled={carregando}
                          onClick={iniciarProximaRodada}
                        >
                          {carregando ? "Iniciando próxima rodada..." : "PRÓXIMA RODADA"}
                        </button>
                        </>
                      ) : (
                        <p role="status">Aguardando um jogador ativo iniciar a próxima rodada...</p>
                      )
                    ) : (
                      <p role="status">10 rodadas concluídas. Preparando resultado final...</p>
                    )}
                  </section>
                )}
              </section>
            )}
            {sala.status === 'AGUARDANDO' && <section className="np-room-code" aria-label="Código da sala">
              <span>Código da sala</span>
              <strong>{sala.codigo}</strong>
              <p>Compartilhe este código com os outros jogadores.</p>
              <button className="button-secondary" type="button" onClick={copiarCodigo}>Copiar código</button>
            </section>}
            {sala.status === 'AGUARDANDO' && <p className="np-room-count">{sala.participantes_ativos} / {sala.limite_jogadores} jogadores</p>}
            {sala.status === 'AGUARDANDO' && <ul className="np-player-list" aria-label="Participantes da sala">
              {participantes.map((participante) => (
                <li key={participante.id} className="np-player">
                  <span aria-hidden="true">{participante.eh_anfitriao ? '♛' : '♙'}</span>
                  <strong>{participante.nome}</strong>
                  {participante.eh_anfitriao && <span className="np-player__badge">Anfitrião</span>}
                  {eu?.id === participante.id && <span className="np-player__you">Você</span>}
                </li>
              ))}
            </ul>}
            {sala.status === 'AGUARDANDO' && (
              <>
                <p className="np-lobby-status">{eu?.eh_anfitriao ? 'Sala pronta para receber jogadores.' : 'Aguardando o anfitrião iniciar a partida.'}</p>
                {eu?.eh_anfitriao && <p className="np-host-note">Você é o anfitrião.</p>}
                {sala.participantes_ativos < 3 && <p className="np-hint">Aguardando pelo menos 3 jogadores.</p>}
                {eu?.eh_anfitriao && (
                  <button
                    className="np-start-button"
                    type="button"
                    disabled={carregando || sala.participantes_ativos < 3 || sala.participantes_ativos > sala.limite_jogadores}
                    onClick={iniciarPartida}
                  >
                    {carregando ? 'Iniciando...' : 'Iniciar partida'}
                  </button>
                )}
              </>
            )}
            {modalSaida && (
              <div className="np-dialog-backdrop" role="presentation">
                <section className="np-dialog" role="dialog" aria-modal="true" aria-labelledby="np-exit-title" aria-describedby="np-exit-description">
                  <p className="np-eyebrow">QuizHub // Sala multiplayer</p>
                  <h4 id="np-exit-title">{modalSaida.tipo === 'bloqueio' ? 'RODADA EM ANDAMENTO' : 'SAIR DA SALA?'}</h4>
                  <p id="np-exit-description">
                    {modalSaida.tipo === 'bloqueio'
                      ? 'Você está em uma rodada em andamento. Para evitar abandonar a partida no meio da rodada, aguarde o resultado para sair da sala.'
                      : 'Você deixará esta partida e não poderá retornar com esta participação.'}
                  </p>
                  {erro && <p className="np-message np-message--error" role="alert">{erro}</p>}
                  <div className="np-dialog__actions">
                    {modalSaida.tipo === 'confirmacao' && (
                      <button className="np-leave" type="button" disabled={carregando} onClick={sairDaSala}>
                        {carregando ? 'Saindo da sala...' : modalSaida.destino === 'home' ? 'SAIR E VOLTAR AO INÍCIO' : 'SAIR DA SALA'}
                      </button>
                    )}
                    <button ref={botaoCancelarSaidaRef} className="button-secondary" type="button" disabled={carregando} onClick={() => setModalSaida(null)}>
                      {modalSaida.tipo === 'bloqueio' ? 'CONTINUAR NA PARTIDA' : 'CANCELAR'}
                    </button>
                  </div>
                </section>
              </div>
            )}
          </>
        )}
      </section>
    )
  }

  return (
    <section className="np-screen" aria-labelledby="np-title" aria-busy={carregando}>
      <header className="np-heading">
        <span className="np-eyebrow">QuizHub // Modo multiplayer</span>
        <h1 id="np-title">NEM A PATO!</h1>
        <p>3–6 jogadores · 10 rodadas · 2 minutos por rodada</p>
        <p className="np-heading__rule">Quem terminar com menos patos vence.</p>
      </header>
      {erro && <p className="np-message np-message--error" role="alert">{erro}</p>}
      {sucesso && <p className="np-message" role="status">{sucesso}</p>}
      {!formulario ? (
        <div className="np-actions">
          <button type="button" onClick={() => { setFormulario('criar'); setErro('') }}>Criar sala</button>
          <button type="button" className="button-secondary" onClick={() => { setFormulario('entrar'); setErro('') }}>Entrar em sala</button>
          <button type="button" className="button-ghost" onClick={voltarInicio}>Voltar ao QuizHub</button>
        </div>
      ) : (
        <form className="np-form" onSubmit={(event) => { event.preventDefault(); iniciarParticipacao(formulario) }}>
          {formulario === 'entrar' && (
            <label htmlFor="np-code">
              Código da sala
              <input
                id="np-code"
                name="codigo"
                value={codigo}
                onChange={(event) => setCodigo(event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
                autoCapitalize="characters"
                autoComplete="off"
                autoCorrect="off"
                inputMode="text"
                spellCheck={false}
                maxLength={6}
                required
              />
            </label>
          )}
          <label htmlFor="np-name">
            Seu nome
            <input
              id="np-name"
              name="nome"
              value={nome}
              onChange={(event) => setNome(event.target.value.slice(0, 100))}
              autoComplete="nickname"
              maxLength={100}
              required
            />
          </label>
          <button type="submit" disabled={carregando}>
            {carregando ? (formulario === 'criar' ? 'Criando sala...' : 'Entrando...') : formulario === 'criar' ? 'Criar sala' : 'Entrar'}
          </button>
          <button type="button" className="button-ghost" disabled={carregando} onClick={() => { setFormulario(null); setErro('') }}>Voltar</button>
        </form>
      )}
    </section>
  )
}

export default TelaNemAPato
