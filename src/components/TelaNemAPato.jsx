import { useCallback, useEffect, useRef, useState } from 'react'
import {
  abandonarSalaNemAPato,
  carregarSessaoNemAPato,
  criarSalaNemAPato,
  entrarSalaNemAPato,
  recuperarSalaNemAPato,
  removerSessaoNemAPato,
  salvarSessaoNemAPato,
} from '../services/nemAPato'

const INTERVALO_LOBBY_MS = 1000

function mensagemErro(error, acao = 'operacao') {
  if (error.message === 'sala inexistente') return 'Sala não encontrada.'
  if (error.message === 'sala cheia') return 'A sala está cheia.'
  if (error.message === 'nome já está em uso na sala') return 'Este nome já está sendo usado.'
  if (error.message === 'sala não está aguardando') return 'Não é mais possível entrar nesta sala.'
  if (error.message === 'credencial Nem a Pato inválida' || error.message === 'credencial Nem a Pato ausente') {
    return 'Sua participação não está mais disponível. Entre na sala novamente.'
  }
  if (error.message === 'participante não está ativo') return 'Sua participação foi encerrada.'
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
  const [sessao, setSessao] = useState(() => {
    const inicial = rotaAtual()
    return inicial.tipo === 'lobby' ? carregarSessaoNemAPato(inicial.codigo) : null
  })
  const [estadoSala, setEstadoSala] = useState(null)
  const [podeSincronizar, setPodeSincronizar] = useState(false)
  const operacaoRef = useRef(false)
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
    const mensagemSemSessao = !sessao && !erro
      ? 'Não há uma participação salva para esta sala neste navegador.'
      : erro
    return (
      <section className="np-screen" aria-labelledby="np-title">
        <header className="np-heading">
          <span className="np-eyebrow">QuizHub // Sala multiplayer</span>
          <h1 id="np-title">NEM A PATO!</h1>
          <p>Lobby da sala</p>
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
            <p className="np-lobby-status">Aguardando a partida...</p>
            {eu?.eh_anfitriao && <p className="np-host-note">Você é o anfitrião.</p>}
            <p className="np-hint">São necessários pelo menos 3 jogadores para uma partida.</p>
            <button className="np-leave" type="button" disabled={carregando} onClick={sairDaSala}>
              {carregando ? 'Saindo...' : 'Sair da sala'}
            </button>
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
