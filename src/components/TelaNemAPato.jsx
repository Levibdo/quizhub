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
import useModalAcessivel from '../hooks/useModalAcessivel'
import NemAPatoEntry from './nem-a-pato/NemAPatoEntry'
import NemAPatoLobby from './nem-a-pato/NemAPatoLobby'

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
  if (error.codigo === 'CATALOGO_OFICIAL_INATIVO') return error.message
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
  const retornoFocoModalRef = useRef(null)
  const codigoSalaRef = useRef(null)
  const fecharDesafio = useCallback(() => setConfirmacaoDesafio(false), [])
  const fecharSaida = useCallback(() => setModalSaida(null), [])
  const { modalRef: modalDesafioRef, aoPressionarTecla: conterFocoDesafio } = useModalAcessivel({ aberto: confirmacaoDesafio, bloqueado: carregando, aoFechar: fecharDesafio, focoInicialRef: botaoCancelarDesafioRef, retornoFocoRef: retornoFocoModalRef })
  const { modalRef: modalSaidaRef, aoPressionarTecla: conterFocoSaida } = useModalAcessivel({ aberto: Boolean(modalSaida), bloqueado: carregando, aoFechar: fecharSaida, focoInicialRef: botaoCancelarSaidaRef, retornoFocoRef: retornoFocoModalRef })

  const navegar = useCallback((destino) => {
    const caminho = destino.tipo === 'lobby'
      ? `/nem-a-pato/sala/${encodeURIComponent(destino.codigo)}`
      : '/nem-a-pato'
    window.history.pushState({ ...window.history.state }, '', caminho)
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
    if (sucesso !== 'Código copiado.') return undefined
    const temporizador = globalThis.setTimeout(() => setSucesso(''), 2500)
    return () => globalThis.clearTimeout(temporizador)
  }, [sucesso])

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

  const solicitarSaida = useCallback((destino = 'modo', evento) => {
    retornoFocoModalRef.current = evento?.currentTarget ?? null
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
    registrarAcaoMarca((evento) => solicitarSaida('home', evento))
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


  function abrirConfirmacaoDesafio(evento) {
    if (!operacaoRef.current) {
      retornoFocoModalRef.current = evento?.currentTarget ?? null
      setConfirmacaoDesafio(true)
    }
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

  function selecionarCodigoManualmente() {
    codigoSalaRef.current?.focus()
    codigoSalaRef.current?.select()
    setSucesso('Não foi possível copiar automaticamente. O código foi selecionado; use o comando de copiar do seu dispositivo.')
  }

  async function copiarCodigo() {
    setSucesso('')
    try {
      const copiar = globalThis.navigator?.clipboard?.writeText
      if (typeof copiar !== 'function') throw new Error('Clipboard indisponível')
      const escrita = copiar.call(globalThis.navigator.clipboard, rota.codigo)
      if (!escrita || typeof escrita.then !== 'function') throw new Error('Cópia não confirmada')
      await escrita
      setSucesso('Código copiado.')
    } catch {
      selecionarCodigoManualmente()
    }
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

    return (
      <NemAPatoLobby
        botaoCancelarDesafioRef={botaoCancelarDesafioRef}
        botaoCancelarSaidaRef={botaoCancelarSaidaRef}
        carregando={carregando}
        codigoSalaRef={codigoSalaRef}
        confirmacaoDesafio={confirmacaoDesafio}
        erro={erro}
        estadoTerminalCompleto={estadoTerminalCompleto}
        eu={eu}
        jogadorAtual={jogadorAtual}
        mensagemSemSessao={mensagemSemSessao}
        modalDesafioRef={modalDesafioRef}
        modalSaida={modalSaida}
        modalSaidaRef={modalSaidaRef}
        palpite={palpite}
        partida={partida}
        participantes={participantes}
        placarFinal={placarFinal}
        podeAbandonar={podeAbandonar}
        podeDesafiar={podeDesafiar}
        prazoEsgotado={prazoEsgotado}
        resultadoFinal={resultadoFinal}
        rodada={rodada}
        sala={sala}
        sessao={sessao}
        sucesso={sucesso}
        tempoExibido={tempoExibido}
        ultimoPalpite={ultimoPalpite}
        aoAlterarPalpite={(valor) => {
          setPalpite(valor.replace(/\D/g, ''))
          acaoPalpiteRef.current = null
        }}
        aoConfirmarDesafio={confirmarDesafio}
        aoConfirmarPalpite={confirmarPalpite}
        aoConterFocoDesafio={conterFocoDesafio}
        aoConterFocoSaida={conterFocoSaida}
        aoCopiarCodigo={copiarCodigo}
        aoFecharDesafio={fecharDesafio}
        aoFecharSaida={fecharSaida}
        aoIniciarPartida={iniciarPartida}
        aoIniciarProximaRodada={iniciarProximaRodada}
        aoIniciarRodada={iniciarRodada}
        aoJogarNovamente={jogarNovamente}
        aoNavegarInicio={() => navegar({ tipo: 'inicio' })}
        aoSairDaSala={sairDaSala}
        aoSolicitarDesafio={abrirConfirmacaoDesafio}
        aoSolicitarSaida={solicitarSaida}
        aoTentarRecuperar={tentarRecuperarSala}
        aoVoltarInicio={() => limparParticipacaoLocal('home')}
      />
    )
  }

  return (
    <NemAPatoEntry
      carregando={carregando}
      codigo={codigo}
      erro={erro}
      formulario={formulario}
      nome={nome}
      sucesso={sucesso}
      aoAlterarCodigo={(valor) => setCodigo(valor.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
      aoAlterarNome={(valor) => setNome(valor.slice(0, 100))}
      aoEscolherFormulario={(valor) => { setFormulario(valor); setErro('') }}
      aoEnviar={iniciarParticipacao}
      aoVoltar={voltarInicio}
    />
  )
}

export default TelaNemAPato
