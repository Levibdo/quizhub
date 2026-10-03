import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { rolldown } from 'rolldown'
const require = createRequire(import.meta.url)
const { act, createElement } = require('react')
const { create } = require('react-test-renderer')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const location = { protocol: 'http:', hostname: 'localhost', pathname: '/nem-a-pato' }
globalThis.window = {
  location,
  history: {
    pushState(_state, _title, path) { location.pathname = path },
  },
  addEventListener() {},
  removeEventListener() {},
  setInterval: globalThis.setInterval,
  clearInterval: globalThis.clearInterval,
}

const bundle = await rolldown({
  input: fileURLToPath(new URL('../src/App.jsx', import.meta.url)),
  platform: 'node',
  transform: { jsx: { runtime: 'automatic' } },
  plugins: [{
    name: 'resources-for-tests',
    resolveId(source) {
      if (source === 'react' || source.startsWith('react/')) {
        return { id: pathToFileURL(require.resolve(source)).href, external: true }
      }
      if (/\.(css|png)$/.test(source)) return '\0ignored-test-resource'
    },
    load(id) { if (id === '\0ignored-test-resource') return 'export default ""' },
  }],
})
const { output } = await bundle.generate({ format: 'es' })
await bundle.close()
const { default: App } = await import(
  `data:text/javascript;base64,${globalThis.Buffer.from(output[0].code).toString('base64')}`
)

function text(node) {
  if (typeof node === 'string') return node
  return (node.children || []).map(text).join('')
}

function setup(t, fetcher, { path = '/nem-a-pato', stored = {} } = {}) {
  const originalFetch = globalThis.fetch
  const originalStorage = globalThis.localStorage
  const storage = new Map(Object.entries(stored))
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  }
  location.pathname = path
  globalThis.window.setInterval = globalThis.setInterval
  globalThis.window.clearInterval = globalThis.clearInterval
  globalThis.fetch = fetcher
  globalThis.window.setInterval = globalThis.setInterval
  globalThis.window.clearInterval = globalThis.clearInterval
  let renderer
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount())
    globalThis.fetch = originalFetch
    globalThis.localStorage = originalStorage
    t.mock.timers.reset()
  })
  return {
    storage,
    render: async () => act(async () => { renderer = create(createElement(App)) }),
    unmount: async () => {
      if (renderer) {
        await act(async () => renderer.unmount())
        renderer = null
      }
    },
    get renderer() { return renderer },
    button(label) {
      return renderer.root.findAllByType('button').find((item) => text(item) === label)
    },
    view() { return text(renderer.root) },
    findInput(label) {
      const labelNode = renderer.root.findAllByType('label').find((item) => text(item).includes(label))
      return labelNode.findByType('input')
    },
  }
}

function response(value, status = 200) {
  return new Response(JSON.stringify(value), { status })
}

function sala(codigo, participantes, versao = 0, status = 'AGUARDANDO') {
  return {
    codigo,
    status,
    versao,
    criada_em: '2026-10-01T12:00:00Z',
    participantes,
    participantes_ativos: participantes.length,
    limite_jogadores: 6,
  }
}

function participante(id, nome, eh_anfitriao = false) {
  return { id, nome, eh_anfitriao, ordem_entrada: id, status: 'ATIVO' }
}

test('home abre a entrada Nem a Pato sem remover Quiz Clássico', async (t) => {
  const ui = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response({}), { path: '/' })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('Quiz Clássico'))
  await act(async () => ui.button('Abrir Nem a Pato').props.onClick())
  assert.ok(ui.view().includes('NEM A PATO!'))
  assert.ok(ui.button('Criar sala'))
  assert.ok(ui.button('Entrar em sala'))
})

test('criar sala persiste token no namespace e entra no lobby sem mostrar token', async (t) => {
  const calls = []
  const token = 'temporary-token-not-rendered'
  const created = {
    sala: sala('K7M4QX', [participante(1, 'Levi', true)]),
    participante: participante(1, 'Levi', true),
    credencial_participante: token,
  }
  const ui = setup(t, async (url, options = {}) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/nem-pato/salas')) return response(created, 201)
    return response({ sala: created.sala, participante: created.participante })
  }, { path: '/' })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  await act(async () => ui.button('Abrir Nem a Pato').props.onClick())
  await act(async () => ui.button('Criar sala').props.onClick())
  await act(async () => {
    ui.findInput('Seu nome').props.onChange({ target: { value: '  Levi  ' } })
  })
  await act(async () => ui.renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
  assert.ok(ui.view().includes('K7M4QX'))
  assert.ok(ui.view().includes('Levi'))
  assert.ok(ui.view().includes('Anfitrião'))
  assert.ok(ui.view().includes('Você'))
  assert.ok(!ui.view().includes(token))
  assert.deepEqual(JSON.parse(ui.storage.get('quizhub-nem-pato-sessoes')), {
    K7M4QX: { codigo: 'K7M4QX', token },
  })
  assert.deepEqual(JSON.parse(calls.find((call) => call.url.endsWith('/nem-pato/salas')).options.body), { nome: 'Levi' })
})

test('entrar normaliza código visual e mostra erro de sala cheia', async (t) => {
  const calls = []
  const ui = setup(t, async (url, options = {}) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/participantes')) return response({ detail: 'sala cheia' }, 409)
    return response({})
  }, { path: '/' })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  await act(async () => ui.button('Abrir Nem a Pato').props.onClick())
  await act(async () => ui.button('Entrar em sala').props.onClick())
  await act(async () => ui.findInput('Código da sala').props.onChange({ target: { value: 'k7m 4qx$' } }))
  await act(async () => ui.findInput('Seu nome').props.onChange({ target: { value: 'Jorge' } }))
  assert.equal(ui.findInput('Código da sala').props.value, 'K7M4QX')
  await act(async () => ui.renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
  assert.ok(calls.some((call) => call.url.endsWith('/K7M4QX/participantes')))
  assert.ok(ui.view().includes('A sala está cheia.'))
})

test('entrar em sala persiste a credencial por código e traduz nome duplicado', async (t) => {
  const token = 'jorge-token'
  const joined = {
    sala: sala('K7M4QX', [participante(1, 'Levi', true), participante(2, 'Jorge')]),
    participante: participante(2, 'Jorge'),
    credencial_participante: token,
  }
  let rejectDuplicate = false
  const ui = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/participantes')) {
      return rejectDuplicate
        ? response({ detail: 'nome já está em uso na sala' }, 409)
        : response(joined, 201)
    }
    return response({})
  }, { path: '/' })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  await act(async () => ui.button('Abrir Nem a Pato').props.onClick())
  await act(async () => ui.button('Entrar em sala').props.onClick())
  await act(async () => ui.findInput('Código da sala').props.onChange({ target: { value: 'k7m4qx' } }))
  await act(async () => ui.findInput('Seu nome').props.onChange({ target: { value: 'Jorge' } }))
  await act(async () => ui.renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
  assert.ok(ui.view().includes('Jorge'))
  assert.deepEqual(JSON.parse(ui.storage.get('quizhub-nem-pato-sessoes')), {
    K7M4QX: { codigo: 'K7M4QX', token },
  })
  await ui.unmount()

  rejectDuplicate = true
  location.pathname = '/'
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  await act(async () => ui.button('Abrir Nem a Pato').props.onClick())
  await act(async () => ui.button('Entrar em sala').props.onClick())
  await act(async () => ui.findInput('Código da sala').props.onChange({ target: { value: 'K7M4QX' } }))
  await act(async () => ui.findInput('Seu nome').props.onChange({ target: { value: 'Jorge' } }))
  await act(async () => ui.renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
  assert.ok(ui.view().includes('Este nome já está sendo usado.'))
})

test('deep link recupera credencial após reload e polling atualiza jogadores', async (t) => {
  const calls = []
  let pollCount = 0
  let pollingCallback
  const token = 'token-jorge'
  const ui = setup(t, async (url, options = {}) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/eu')) {
      pollCount += 1
      const jogadores = [participante(1, 'Levi', true), participante(2, 'Jorge')]
      if (pollCount >= 2) jogadores.push(participante(3, 'Luana'))
      return response({ sala: sala('K7M4QX', jogadores, pollCount), participante: jogadores[1] })
    }
    throw new Error(`unexpected request ${url}`)
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token } }) },
  })
  globalThis.window.setInterval = (callback, delay) => {
    assert.equal(delay, 1000)
    pollingCallback = callback
    return 41
  }
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('Jorge'))
  assert.ok(ui.view().includes('Anfitrião'))
  assert.ok(calls.some((call) => call.url.endsWith('/eu') && call.options.headers['X-Nem-Pato-Token'] === token))
  assert.equal(typeof pollingCallback, 'function')
  await act(async () => pollingCallback())
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('Luana'))
  assert.equal(calls.filter((call) => call.url.endsWith('/eu')).length, 2)
  assert.equal(calls.some((call) => call.url.endsWith('/abandonar')), false)
})

test('credencial inválida é removida e oferece retorno ao fluxo do modo', async (t) => {
  const token = 'revoked-token'
  const ui = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response({ detail: 'credencial Nem a Pato inválida' }, 401), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token } }) },
  })
  await ui.render()
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  assert.ok(ui.view().includes('Sua participação não está mais disponível'))
  assert.deepEqual(JSON.parse(ui.storage.get('quizhub-nem-pato-sessoes')), {})
  assert.ok(ui.button('Voltar para Nem a Pato'))
})

test('sair remove somente credencial da sala atual', async (t) => {
  const token = 'current-token'
  const ui = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/eu')) return response({
      sala: sala('K7M4QX', [participante(1, 'Levi', true)]),
      participante: participante(1, 'Levi', true),
    })
    if (url.endsWith('/abandonar')) return response(sala('K7M4QX', []))
    throw new Error(`unexpected ${url}`)
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({
      K7M4QX: { codigo: 'K7M4QX', token },
      ABC234: { codigo: 'ABC234', token: 'other-token' },
    }) },
  })
  await ui.render()
  await act(async () => ui.button('Sair da sala').props.onClick())
  assert.deepEqual(JSON.parse(ui.storage.get('quizhub-nem-pato-sessoes')), {
    ABC234: { codigo: 'ABC234', token: 'other-token' },
  })
  assert.ok(ui.view().includes('Você saiu da sala.'))
})

test('polling é limpo ao desmontar lobby', async (t) => {
  let chamadasLobby = 0
  let pollingCallback
  let intervaloLimpo = false
  const ui = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/eu')) {
      chamadasLobby += 1
      return response({ sala: sala('K7M4QX', [participante(1, 'Levi', true)]), participante: participante(1, 'Levi', true) })
    }
    return response({})
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'token' } }) },
  })
  globalThis.window.setInterval = (callback, delay) => {
    assert.equal(delay, 1000)
    pollingCallback = callback
    return 42
  }
  globalThis.window.clearInterval = (id) => { intervaloLimpo = id === 42 }
  await ui.render()
  await act(async () => Promise.resolve())
  const beforeUnmount = chamadasLobby
  await ui.unmount()
  await act(async () => pollingCallback())
  assert.equal(chamadasLobby, beforeUnmount)
  assert.equal(intervaloLimpo, true)
})

test('host vê início desabilitado com menos de três e habilitado ao atingir mínimo', async (t) => {
  let quantidade = 2
  const token = 'host-start-token'
  const ui = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    const jogadores = Array.from({ length: quantidade }, (_, index) =>
      participante(index + 1, `Jogador ${index + 1}`, index === 0))
    return response({
      sala: sala('K7M4QX', jogadores, quantidade, 'AGUARDANDO'),
      participante: jogadores[0],
      partida: null,
    })
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({
      K7M4QX: { codigo: 'K7M4QX', token },
    }) },
  })
  globalThis.window.setInterval = (callback) => { globalThis.np4Poll = callback; return 71 }
  globalThis.window.clearInterval = () => {}
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(ui.button('Iniciar partida').props.disabled, true)
  quantidade = 3
  await act(async () => globalThis.np4Poll())
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(ui.button('Iniciar partida').props.disabled, false)
})

test('host inicia com token; polling e F5 mostram preparação EM_PARTIDA', async (t) => {
  const token = 'host-token'
  const jogadores = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const partida = {
    id: 'match-uuid', numero: 1, status: 'EM_ANDAMENTO', rodada_atual: 0,
    total_rodadas: 10, duracao_rodada_segundos: 120,
    jogadores: jogadores.map((jogador, index) => ({
      id: `snapshot-${index + 1}`, nome: jogador.nome, ordem_circular: index + 1, status: 'ATIVO', eh_eu: index === 0,
    })),
    rodada: { id: 11, numero: 1, status: 'AGUARDANDO_INICIO' },
  }
  let emPartida = false
  let tokenEnviado
  const chamadas = []
  const fetcher = async (url, options = {}) => {
    chamadas.push({ url, options })
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/iniciar')) {
      tokenEnviado = options.headers['X-Nem-Pato-Token']
      emPartida = true
      return response({
        sala: sala('K7M4QX', jogadores, 4, 'EM_PARTIDA'),
        participante: jogadores[0], partida,
      })
    }
    if (url.endsWith('/eu')) {
      return response({
        sala: sala('K7M4QX', jogadores, emPartida ? 4 : 3, emPartida ? 'EM_PARTIDA' : 'AGUARDANDO'),
        participante: jogadores[0],
        partida: emPartida ? partida : null,
      })
    }
    return response({})
  }
  const ui = setup(t, fetcher, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(ui.button('Iniciar partida').props.disabled, false)
  await act(async () => ui.button('Iniciar partida').props.onClick())
  assert.equal(tokenEnviado, token)
  assert.ok(ui.view().includes('A PARTIDA COMEÇOU'))
  assert.ok(ui.view().includes('10 rodadas'))
  assert.ok(ui.view().includes('2 minutos por rodada'))
  assert.ok(!ui.view().includes('Sair da sala'))
  assert.equal(chamadas.some((call) => call.url.endsWith('/perguntas')), false)
  await ui.unmount()

  const reloaded = setup(t, fetcher, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token } }) },
  })
  await reloaded.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(reloaded.view().includes('A PARTIDA COMEÇOU'))
  assert.ok(reloaded.view().includes('Jorge'))
  assert.ok(reloaded.button('Iniciar rodada'))
})

test('não host não tem botão de início e o host vê erro retornado pelo backend', async (t) => {
  let requisicoesInicio = 0
  const guest = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    return response({
      sala: sala('K7M4QX', [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]),
      participante: participante(2, 'Jorge'), partida: null,
    })
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'guest-token' } }) },
  })
  await guest.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(guest.button('Iniciar partida'), undefined)
  await guest.unmount()

  const host = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/iniciar')) {
      requisicoesInicio += 1
      return response({ detail: 'não há 10 perguntas Nem a Pato ativas disponíveis' }, 409)
    }
    return response({
      sala: sala('K7M4QX', [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]),
      participante: participante(1, 'Levi', true), partida: null,
    })
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host-token' } }) },
  })
  await host.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  await act(async () => host.button('Iniciar partida').props.onClick())
  assert.equal(requisicoesInicio, 1)
  assert.ok(host.view().includes('Ainda não há 10 perguntas numéricas ativas'))
})

test('somente host pode iniciar e botão fica desabilitado abaixo do mínimo', async (t) => {
  const hostUI = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    return response({
      sala: sala('K7M4QX', [participante(1, 'Levi', true), participante(2, 'Jorge')]),
      participante: participante(1, 'Levi', true),
      partida: null,
    })
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host-token' } }) },
  })
  await hostUI.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(hostUI.button('Iniciar partida').props.disabled, true)
  assert.ok(hostUI.view().includes('pelo menos 3'))
  await hostUI.unmount()

  const guestUI = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    return response({
      sala: sala('K7M4QX', [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]),
      participante: participante(2, 'Jorge'),
      partida: null,
    })
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'guest-token' } }) },
  })
  await guestUI.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(guestUI.button('Iniciar partida'), undefined)
  assert.ok(guestUI.view().includes('Aguardando o anfitrião'))
})

test('host inicia com credencial e todos recuperam tela EM_PARTIDA após F5', async (t) => {
  const token = 'host-token'
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const summary = {
    id: 'match-id', numero: 1, status: 'EM_ANDAMENTO', rodada_atual: 0,
    total_rodadas: 10, duracao_rodada_segundos: 120,
    jogadores: players.map((player, index) => ({
      id: `snapshot-${index + 1}`, nome: player.nome, ordem_circular: index + 1, status: 'ATIVO', eh_eu: index === 0,
    })),
    rodada: { id: 11, numero: 1, status: 'AGUARDANDO_INICIO' },
  }
  let started = false
  const calls = []
  const fetcher = async (url, options = {}) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/iniciar')) {
      started = true
      return response({
        sala: sala('K7M4QX', players, 4, 'EM_PARTIDA'),
        participante: players[0],
        partida: summary,
      })
    }
    if (url.endsWith('/eu')) {
      return response({
        sala: sala('K7M4QX', players, started ? 4 : 3, started ? 'EM_PARTIDA' : 'AGUARDANDO'),
        participante: players[0],
        partida: started ? summary : null,
      })
    }
    return response({})
  }
  const ui = setup(t, fetcher, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.button('Iniciar partida'))
  await act(async () => ui.button('Iniciar partida').props.onClick())
  assert.equal(calls.find((call) => call.url.endsWith('/iniciar')).options.headers['X-Nem-Pato-Token'], token)
  assert.ok(ui.view().includes('A PARTIDA COMEÇOU'))
  assert.ok(ui.view().includes('10 rodadas'))
  assert.ok(ui.view().includes('2 minutos por rodada'))
  assert.equal(ui.button('Sair da sala'), undefined)
  await ui.unmount()

  const reloaded = setup(t, fetcher, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token } }) },
  })
  await reloaded.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(reloaded.view().includes('A PARTIDA COMEÇOU'))
  assert.ok(reloaded.button('Iniciar rodada'))
})

function partidaNp5(players, euId, rodadaStatus = 'AGUARDANDO_INICIO', palpites = []) {
  const snapshots = players.map((player, index) => ({
    id: `snapshot-${index + 1}`,
    nome: player.nome,
    ordem_circular: index + 1,
    status: 'ATIVO',
    eh_eu: player.id === euId,
  }))
  const indiceTurno = palpites.length % snapshots.length
  return {
    id: 'match-np5', numero: 1, status: 'EM_ANDAMENTO',
    rodada_atual: rodadaStatus === 'EM_ANDAMENTO' ? 1 : 0,
    total_rodadas: 10, duracao_rodada_segundos: 120,
    jogadores: snapshots,
    rodada: {
      id: 51,
      numero: 1,
      status: rodadaStatus,
      pergunta: rodadaStatus === 'EM_ANDAMENTO'
        ? { id: 9, categoria_id: 'geral', enunciado: 'Quantos quilômetros tem a Terra?', unidade: 'km' }
        : null,
      jogador_inicial: snapshots[0],
      jogador_da_vez: rodadaStatus === 'EM_ANDAMENTO' ? snapshots[indiceTurno] : null,
      maior_palpite: palpites.length ? palpites.at(-1).valor : null,
      palpites: palpites.map((item, index) => ({
        ordem: index + 1,
        valor: item.valor,
        jogador: snapshots[item.jogador],
        criado_em: '2026-10-03T12:00:00Z',
      })),
      iniciada_em: rodadaStatus === 'EM_ANDAMENTO' ? '2026-10-03T12:00:00Z' : null,
      termina_em: rodadaStatus === 'EM_ANDAMENTO' ? '2026-10-03T12:02:00Z' : null,
    },
  }
}

test('host vê Iniciar rodada e não-host aguarda o anfitrião', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const estado = (eu) => ({
    sala: sala('K7M4QX', players, 4, 'EM_PARTIDA'),
    participante: players[eu - 1],
    partida: partidaNp5(players, eu),
  })
  const host = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(estado(1)), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host' } }) },
  })
  await host.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(host.button('Iniciar rodada'))
  await host.unmount()

  const guest = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(estado(2)), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'guest' } }) },
  })
  await guest.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(guest.button('Iniciar rodada'), undefined)
  assert.ok(guest.view().includes('Aguardando o anfitrião iniciar a rodada'))
})

test('host inicia rodada, envia ação idempotente e turno/histórico atualizam', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  let partida = partidaNp5(players, 1)
  let payloadPalpite
  let concluirPalpite
  const calls = []
  const ui = setup(t, async (url, options = {}) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/rodadas/iniciar')) {
      partida = partidaNp5(players, 1, 'EM_ANDAMENTO')
    } else if (url.endsWith('/palpites')) {
      payloadPalpite = JSON.parse(options.body)
      return new Promise((resolve) => {
        concluirPalpite = () => {
          partida = partidaNp5(players, 1, 'EM_ANDAMENTO', [{ jogador: 0, valor: payloadPalpite.valor }])
          resolve(response({
            sala: sala('K7M4QX', players, 5, 'EM_PARTIDA'),
            participante: players[0],
            partida,
          }))
        }
      })
    }
    return response({
      sala: sala('K7M4QX', players, 5, 'EM_PARTIDA'),
      participante: players[0],
      partida,
    })
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host-token' } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  await act(async () => ui.button('Iniciar rodada').props.onClick())
  assert.ok(ui.view().includes('Quantos quilômetros tem a Terra?'))
  assert.ok(ui.view().includes('Rodada 1 de 10'))
  assert.ok(ui.view().includes('Jogador da vez'))
  assert.ok(ui.view().includes('Levi'))
  assert.ok(!ui.view().includes('resposta_numerica'))
  assert.ok(!ui.view().includes('explicacao'))
  const input = ui.renderer.root.findByProps({ id: 'np-guess' })
  await act(async () => input.props.onChange({ target: { value: '100' } }))
  let envio
  await act(async () => {
    envio = ui.renderer.root.findAllByType('form').find((form) => form.props.className === 'np-guess-form').props.onSubmit({ preventDefault() {} })
    await Promise.resolve()
  })
  assert.equal(ui.button('Enviando...').props.disabled, true)
  await act(async () => {
    concluirPalpite()
    await envio
  })
  assert.equal(payloadPalpite.valor, 100)
  assert.match(payloadPalpite.client_action_id, /^[0-9a-f-]{36}$/)
  assert.ok(calls.some((call) => call.url.endsWith('/rodadas/51/palpites')))
  assert.ok(ui.view().includes('Maior palpite'))
  assert.ok(ui.view().includes('100 km'))
  assert.ok(ui.view().includes('Levi100 km'))
  assert.ok(ui.view().includes('Jogador da vez'))
  assert.ok(ui.view().includes('Jorge'))
  assert.equal(ui.renderer.root.findAllByProps({ id: 'np-guess' }).length, 0)
  assert.ok(ui.view().includes('Aguardando o palpite de Jorge'))
})

test('erro de palpite crescente é amigável e F5 recupera rodada ativa', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const ativa = partidaNp5(players, 2, 'EM_ANDAMENTO', [{ jogador: 0, valor: 100 }])
  const ui = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/palpites')) return response({ detail: 'seu palpite precisa ser maior que 100' }, 409)
    return response({
      sala: sala('K7M4QX', players, 6, 'EM_PARTIDA'),
      participante: players[1],
      partida: ativa,
    })
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'jorge-token' } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('Quantos quilômetros tem a Terra?'))
  assert.ok(ui.view().includes('Maior palpite'))
  assert.ok(ui.view().includes('100 km'))
  assert.ok(ui.renderer.root.findByProps({ id: 'np-guess' }))
  await act(async () => ui.renderer.root.findByProps({ id: 'np-guess' }).props.onChange({ target: { value: '100' } }))
  await act(async () => ui.renderer.root.findAllByType('form').find((form) => form.props.className === 'np-guess-form').props.onSubmit({ preventDefault() {} }))
  assert.ok(ui.view().includes('Seu palpite precisa ser maior que 100.'))
})
