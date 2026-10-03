import { useCallback, useEffect, useRef, useState } from 'react'
import {
  abandonarSalaNemAPato,
  carregarSessaoNemAPato,
  criarSalaNemAPato,
  desafiarPalpiteNemAPato,
  entrarSalaNemAPato,
  enviarPalpiteNemAPato,
  iniciarPartidaNemAPato,
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

function TelaNemAPato({ voltarInicio }) {
  const [rota, setRota] = useState(() => rotaAtual())
  const [formulario, setFormulario] = useState(null)
  const [nome, setNome] = useState('')
  const [codigo, setCodigo] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [palpite, setPalpite] = useState('')
  const [segundosRestantes, setSegundosRestantes] = useState(0)
  const [sessao, setSessao] = useState(() => {
    const inicial = rotaAtual()
    return inicial.tipo === 'lobby' ? carregarSessaoNemAPato(inicial.codigo) : null
  })
  const [estadoSala, setEstadoSala] = useState(null)
  const [podeSincronizar, setPodeSincronizar] = useState(false)
  const operacaoRef = useRef(false)
  const acaoPalpiteRef = useRef(null)
  const acaoDesafioRef = useRef(null)
  const recuperacaoInicial = useRef(false)

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
    if (rota.tipo !== 'lobby' || !sessao || !podeSincronizar) return undefined
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
  }, [rota, sessao, podeSincronizar, atualizarEstado])

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

  async function sairDaSala() {
    if (operacaoRef.current || !sessao) return
    operacaoRef.current = true
    setCarregando(true)
    setErro('')
    try {
      await abandonarSalaNemAPato(sessao.codigo, sessao.token)
      removerSessaoNemAPato(sessao.codigo)
      setSessao(null)
      setEstadoSala(null)
      setPodeSincronizar(false)
      recuperacaoInicial.current = true
      navegar({ tipo: 'inicio' })
      setSucesso('Você saiu da sala.')
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


  async function confirmarDesafio() {
    const rodada = estadoSala?.partida?.rodada
    const ultimo = rodada?.palpites?.at(-1)
    if (operacaoRef.current || !sessao || !rodada || !ultimo) return
    const confirmado = globalThis.window.confirm
      ? globalThis.window.confirm(
        `Desafiar o palpite de ${ultimo.jogador.nome}: ${formatarPalpite(ultimo.valor, rodada.pergunta?.unidade)}?`,
      )
      : true
    if (!confirmado) return
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
    const ultimoPalpite = rodada?.palpites?.at(-1)
    const jogadorAtual = partida?.jogadores?.find((jogador) => jogador.eh_eu)
    const podeDesafiar = rodada?.status === 'EM_ANDAMENTO'
      && ultimoPalpite
      && !ultimoPalpite.jogador.eh_eu
      && jogadorAtual?.status === 'ATIVO'
    const mensagemSemSessao = !sessao && !erro
      ? 'Não há uma participação salva para esta sala neste navegador.'
      : erro
    return (
      <section className="np-screen" aria-labelledby="np-title">
        <header className="np-heading">
          <span className="np-eyebrow">QuizHub // Sala multiplayer</span>
          <h1 id="np-title">NEM A PATO!</h1>
          <p>{sala?.status === 'EM_PARTIDA' ? 'Partida em andamento' : 'Lobby da sala'}</p>
        </header>
        {mensagemSemSessao && <p className="np-message np-message--error" role="alert">{mensagemSemSessao}</p>}
        {sucesso && <p className="np-message" role="status">{sucesso}</p>}
        {!sala && sessao && !erro && <p role="status">Recuperando sua participação...</p>}
        {!sessao && (
          <button className="button-secondary" type="button" onClick={() => navegar({ tipo: 'inicio' })}>
            Voltar para Nem a Pato
          </button>
        )}
        {sala && (
          <>
            {sala.status === 'EM_PARTIDA' && (
              <section className="np-started" aria-labelledby="np-started-title">
                <p className="np-started__eyebrow">Sala {sala.codigo}</p>
                <h2 id="np-started-title">A PARTIDA COMEÇOU</h2>
                {partida ? (
                  <>
                    <p>Partida {partida.numero} · {partida.total_rodadas} rodadas · {Math.floor(partida.duracao_rodada_segundos / 60)} minutos por rodada</p>
                    <ul className="np-player-list" aria-label="Jogadores desta partida">
                      {partida.jogadores.map((jogador) => (
                        <li className="np-player" key={`${jogador.ordem_circular}-${jogador.nome}`}>
                          <span aria-hidden="true">♙</span>
                          <strong>{jogador.nome}</strong>
                        </li>
                      ))}
                    </ul>
                    <section className="np-score" aria-label="Placar de patos">
                      <h3>PATOS</h3>
                      <ul>
                        {partida.jogadores.map((jogador) => (
                          <li key={jogador.id}>
                            <span>{jogador.nome}</span>
                            <strong>{jogador.patos ?? 0} 🦆</strong>
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
                    <p className="np-round__counter">Rodada {rodada.numero} de {partida.total_rodadas}</p>
                    <h3 id="np-round-title">Pergunta</h3>
                    <p className="np-round__question">{rodada.pergunta?.enunciado}</p>
                    {rodada.pergunta?.unidade && <p className="np-round__unit">Unidade: {rodada.pergunta.unidade}</p>}
                    <div className="np-round__status">
                      <p>Maior palpite <strong>{formatarPalpite(rodada.maior_palpite, rodada.pergunta?.unidade)}</strong></p>
                      <p>Jogador da vez <strong>{rodada.jogador_da_vez?.nome}</strong></p>
                      <p className={segundosRestantes <= 10 ? "np-timer np-timer--urgent" : "np-timer"}>Tempo da rodada <strong>{formatarTempo(segundosRestantes)}</strong></p>
                    </div>
                    {segundosRestantes === 0 && <p role="status">TEMPO ESGOTADO — confirmando resultado...</p>}
                    {rodada.palpites.length > 0 && (
                      <ol className="np-guess-history" aria-label="Histórico de palpites">
                        {rodada.palpites.map((item) => (
                          <li key={item.ordem}>
                            <span>{item.jogador.nome}</span>
                            <strong>{formatarPalpite(item.valor, rodada.pergunta?.unidade)}</strong>
                          </li>
                        ))}
                      </ol>
                    )}
                    {rodada.jogador_da_vez?.eh_eu ? (
                      <form className="np-guess-form" onSubmit={confirmarPalpite}>
                        <label htmlFor="np-guess">Seu palpite</label>
                        <input
                          id="np-guess"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          value={palpite}
                          onChange={(event) => {
                            setPalpite(event.target.value.replace(/\D/g, ''))
                            acaoPalpiteRef.current = null
                          }}
                          disabled={carregando}
                          required
                        />
                        <button type="submit" disabled={carregando || !palpite}>
                          {carregando ? 'Enviando...' : 'Confirmar palpite'}
                        </button>
                      </form>
                    ) : (
                      <p role="status">Aguardando o palpite de {rodada.jogador_da_vez?.nome}...</p>
                    )}
                    {podeDesafiar && (
                      <button
                        className="np-challenge"
                        type="button"
                        disabled={carregando}
                        onClick={confirmarDesafio}
                      >
                        {carregando ? "Desafiando..." : "NEM A PATO!"}
                      </button>
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
                      eu?.eh_anfitriao ? (
                        <button
                          className="np-start-button"
                          type="button"
                          disabled={carregando}
                          onClick={iniciarProximaRodada}
                        >
                          {carregando ? "Iniciando próxima rodada..." : "PRÓXIMA RODADA"}
                        </button>
                      ) : (
                        <p role="status">Aguardando o host iniciar a próxima rodada...</p>
                      )
                    ) : (
                      <p role="status">10 rodadas concluídas. Preparando resultado final...</p>
                    )}
                  </section>
                )}
              </section>
            )}
            <section className="np-room-code" aria-label="Código da sala">
              <span>Código da sala</span>
              <strong>{sala.codigo}</strong>
              <p>Compartilhe este código com os outros jogadores.</p>
              <button className="button-secondary" type="button" onClick={copiarCodigo}>Copiar código</button>
            </section>
            <p className="np-room-count">{sala.participantes_ativos} / {sala.limite_jogadores} jogadores</p>
            <ul className="np-player-list" aria-label="Participantes da sala">
              {participantes.map((participante) => (
                <li key={participante.id} className="np-player">
                  <span aria-hidden="true">{participante.eh_anfitriao ? '♛' : '♙'}</span>
                  <strong>{participante.nome}</strong>
                  {participante.eh_anfitriao && <span className="np-player__badge">Anfitrião</span>}
                  {eu?.id === participante.id && <span className="np-player__you">Você</span>}
                </li>
              ))}
            </ul>
            {sala.status !== 'EM_PARTIDA' && (
              <>
                <p className="np-lobby-status">Aguardando o anfitrião...</p>
                {eu?.eh_anfitriao && <p className="np-host-note">Você é o anfitrião.</p>}
                <p className="np-hint">São necessários pelo menos 3 jogadores para iniciar.</p>
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
                <button className="np-leave" type="button" disabled={carregando} onClick={sairDaSala}>
                  {carregando ? 'Aguarde...' : 'Sair da sala'}
                </button>
              </>
            )}
          </>
        )}
      </section>
    )
  }

  return (
    <section className="np-screen" aria-labelledby="np-title">
      <header className="np-heading">
        <span className="np-eyebrow">QuizHub // Modo multiplayer</span>
        <h1 id="np-title">NEM A PATO!</h1>
        <p>Reúna de 3 a 6 jogadores para o desafio.</p>
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
            {carregando ? 'Aguarde...' : formulario === 'criar' ? 'Criar sala' : 'Entrar'}
          </button>
          <button type="button" className="button-ghost" disabled={carregando} onClick={() => { setFormulario(null); setErro('') }}>Voltar</button>
        </form>
      )}
    </section>
  )
}

export default TelaNemAPato
