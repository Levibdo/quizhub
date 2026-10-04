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


function partidaNp6(players, euId, status = "EM_ANDAMENTO") {
  const base = partidaNp5(players, euId, "EM_ANDAMENTO", [{ jogador: 0, valor: 500 }])
  base.jogadores = base.jogadores.map((jogador) => ({ ...jogador, patos: jogador.nome === "Luana" && status === "RESULTADO" ? 1 : 0 }))
  base.rodada.jogador_inicial = base.jogadores[0]
  base.rodada.jogador_da_vez = status === "EM_ANDAMENTO" ? base.jogadores[1] : null
  base.rodada.palpites[0].jogador = base.jogadores[0]
  if (status === "RESULTADO") {
    base.rodada.status = "RESULTADO"
    base.rodada.pergunta = {
      ...base.rodada.pergunta,
      resposta_numerica: 2300,
      explicacao: "Explicação oficial da resposta.",
    }
    base.rodada.finalizada_em = "2026-10-03T12:01:00Z"
    base.rodada.tipo_finalizacao = "DESAFIO"
    base.rodada.resultado_desafio = {
      desafiante: base.jogadores[2],
      palpite_desafiado: base.rodada.palpites[0],
      jogador_penalizado: base.jogadores[2],
      resolvido_em: "2026-10-03T12:01:00Z",
    }
  }
  return base
}

test("botão desafia fora de turno, confirma autor/valor e bloqueia durante request", async (t) => {
  const players = [participante(1, "Levi", true), participante(2, "Jorge"), participante(3, "Luana")]
  let partida = partidaNp6(players, 3)
  let resolver
  let payload
  const confirmacoes = []
  const confirmOriginal = globalThis.window.confirm
  globalThis.window.confirm = (mensagem) => { confirmacoes.push(mensagem); return true }
  t.after(() => { globalThis.window.confirm = confirmOriginal })
  const ui = setup(t, async (url, options = {}) => {
    if (url.endsWith("/auth/me")) return response({ detail: "não autenticado" }, 401)
    if (url.endsWith("/desafiar")) {
      payload = JSON.parse(options.body)
      return new Promise((resolve) => {
        resolver = () => {
          partida = partidaNp6(players, 3, "RESULTADO")
          resolve(response({
            sala: sala("K7M4QX", players, 7, "EM_PARTIDA"),
            participante: players[2],
            partida,
          }))
        }
      })
    }
    return response({
      sala: sala("K7M4QX", players, 6, "EM_PARTIDA"),
      participante: players[2],
      partida,
    })
  }, {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "luana-token" } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.button("NEM A PATO!"))
  let envio
  await act(async () => {
    envio = ui.button("NEM A PATO!").props.onClick()
    await Promise.resolve()
  })
  assert.match(confirmacoes[0], /Levi: 500 km/)
  assert.equal(ui.button("Desafiando...").props.disabled, true)
  await act(async () => { resolver(); await envio })
  assert.match(payload.client_action_id, /^[0-9a-f-]{36}$/)
  assert.ok(ui.view().includes("Resposta correta"))
  assert.ok(ui.view().includes("2.300 km"))
  assert.ok(ui.view().includes("Explicação oficial"))
  assert.ok(ui.view().includes("Luana recebeu 1 pato"))
  assert.equal(ui.button("NEM A PATO!"), undefined)
  assert.equal(ui.renderer.root.findAllByProps({ id: "np-guess" }).length, 0)
})

test("autor não desafia, cancelar não envia e F5 recompõe resultado e placar", async (t) => {
  const players = [participante(1, "Levi", true), participante(2, "Jorge"), participante(3, "Luana")]
  let chamadas = 0
  const confirmOriginal = globalThis.window.confirm
  globalThis.window.confirm = () => false
  t.after(() => { globalThis.window.confirm = confirmOriginal })
  const estadoAtivo = {
    sala: sala("K7M4QX", players, 6, "EM_PARTIDA"),
    participante: players[1],
    partida: partidaNp6(players, 2),
  }
  const ui = setup(t, async (url) => {
    if (url.endsWith("/auth/me")) return response({ detail: "não autenticado" }, 401)
    if (url.endsWith("/desafiar")) chamadas += 1
    return response(estadoAtivo)
  }, {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "jorge-token" } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.button("NEM A PATO!"))
  await act(async () => ui.button("NEM A PATO!").props.onClick())
  assert.equal(chamadas, 0)
  await ui.unmount()

  const resultado = {
    sala: sala("K7M4QX", players, 7, "EM_PARTIDA"),
    participante: players[2],
    partida: partidaNp6(players, 3, "RESULTADO"),
  }
  const reloaded = setup(t, async (url) => url.endsWith("/auth/me")
    ? response({ detail: "não autenticado" }, 401)
    : response(resultado), {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "luana-token" } }) },
  })
  await reloaded.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(reloaded.view().includes("RESULTADO"))
  assert.ok(reloaded.view().includes("Luana1 🦆"))
  assert.ok(reloaded.view().includes("Aguardando o host iniciar a próxima rodada"))
  assert.equal(reloaded.button("NEM A PATO!"), undefined)
})


test("autor do último palpite não vê botão de desafio", async (t) => {
  const players = [participante(1, "Levi", true), participante(2, "Jorge"), participante(3, "Luana")]
  const estado = {
    sala: sala("K7M4QX", players, 6, "EM_PARTIDA"),
    participante: players[0],
    partida: partidaNp6(players, 1),
  }
  const ui = setup(t, async (url) => url.endsWith("/auth/me")
    ? response({ detail: "não autenticado" }, 401)
    : response(estado), {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "levi-token" } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(ui.button("NEM A PATO!"), undefined)
  assert.ok(ui.view().includes("Levi500 km"))
})


test("host avança com um clique e recebe R2 limpa com placar preservado", async (t) => {
  const players = [participante(1, "Levi", true), participante(2, "Jorge"), participante(3, "Luana")]
  let partida = partidaNp6(players, 1, "RESULTADO")
  let resolver
  const ui = setup(t, async (url) => {
    if (url.endsWith("/auth/me")) return response({ detail: "não autenticado" }, 401)
    if (url.endsWith("/proxima")) {
      return new Promise((resolve) => {
        resolver = () => {
          const patos = partida.jogadores.map((jogador) => jogador.patos)
          partida = partidaNp5(players, 1, "EM_ANDAMENTO", [])
          partida.rodada.numero = 2
          partida.rodada.pergunta = { id: 10, categoria_id: "geral", enunciado: "Pergunta inédita da rodada 2", unidade: "itens" }
          partida.rodada.jogador_inicial = partida.jogadores[1]
          partida.rodada.jogador_da_vez = partida.jogadores[1]
          partida.jogadores = partida.jogadores.map((jogador, indice) => ({ ...jogador, patos: patos[indice] }))
          resolve(response({ sala: sala("K7M4QX", players, 8, "EM_PARTIDA"), participante: players[0], partida }))
        }
      })
    }
    return response({ sala: sala("K7M4QX", players, 7, "EM_PARTIDA"), participante: players[0], partida })
  }, {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "host-token" } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.button("PRÓXIMA RODADA"))
  let envio
  await act(async () => { envio = ui.button("PRÓXIMA RODADA").props.onClick(); await Promise.resolve() })
  assert.equal(ui.button("Iniciando próxima rodada...").props.disabled, true)
  await act(async () => { resolver(); await envio })
  assert.ok(ui.view().includes("Rodada 2 de 10"))
  assert.ok(ui.view().includes("Pergunta inédita da rodada 2"))
  assert.ok(ui.view().includes("Jogador da vez"))
  assert.ok(ui.view().includes("Jorge"))
  assert.ok(ui.view().includes("Luana1 🦆"))
  assert.ok(!ui.view().includes("Resposta correta"))
  assert.ok(!ui.view().includes("500 km"))
})

test("não-host sincroniza R2 por polling e rodada 10 não oferece avanço", async (t) => {
  const players = [participante(1, "Levi", true), participante(2, "Jorge"), participante(3, "Luana")]
  let partida = partidaNp6(players, 2, "RESULTADO")
  let pollingCallback
  const ui = setup(t, async (url) => {
    if (url.endsWith("/auth/me")) return response({ detail: "não autenticado" }, 401)
    return response({ sala: sala("K7M4QX", players, 7, "EM_PARTIDA"), participante: players[1], partida })
  }, {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "jorge-token" } }) },
  })
  globalThis.window.setInterval = (callback) => { pollingCallback = callback; return 96 }
  globalThis.window.clearInterval = () => {}
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(ui.button("PRÓXIMA RODADA"), undefined)
  assert.ok(ui.view().includes("Aguardando o host iniciar a próxima rodada"))
  partida = partidaNp5(players, 2, "EM_ANDAMENTO", [])
  partida.rodada.numero = 2
  partida.rodada.pergunta = { id: 10, categoria_id: "geral", enunciado: "Pergunta após polling", unidade: null }
  partida.rodada.jogador_inicial = partida.jogadores[1]
  partida.rodada.jogador_da_vez = partida.jogadores[1]
  await act(async () => pollingCallback())
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes("Rodada 2 de 10"))
  assert.ok(ui.view().includes("Pergunta após polling"))
  await ui.unmount()

  const final = partidaNp6(players, 1, "RESULTADO")
  final.rodada.numero = 10
  const host = setup(t, async (url) => url.endsWith("/auth/me")
    ? response({ detail: "não autenticado" }, 401)
    : response({ sala: sala("K7M4QX", players, 20, "EM_PARTIDA"), participante: players[0], partida: final }), {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "host-token" } }) },
  })
  await host.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(host.button("PRÓXIMA RODADA"), undefined)
  assert.ok(host.view().includes("10 rodadas concluídas"))
})


function partidaTimeout(players, euId, comPalpite = true) {
  const base = partidaNp5(players, euId, "EM_ANDAMENTO", comPalpite ? [{ jogador: 2, valor: 700 }] : [])
  base.rodada.status = "RESULTADO"
  base.rodada.jogador_da_vez = null
  base.rodada.pergunta = { ...base.rodada.pergunta, resposta_numerica: 900, explicacao: "Explicação do timeout." }
  base.rodada.finalizada_em = "2026-10-03T12:02:01Z"
  base.rodada.tipo_finalizacao = comPalpite ? "TEMPO_ESGOTADO" : "SEM_PALPITE"
  base.rodada.resultado_timeout = {
    ultimo_palpite: comPalpite ? base.rodada.palpites.at(-1) : null,
    autor_protegido: comPalpite ? base.jogadores[2] : null,
  }
  base.jogadores = base.jogadores.map((jogador, indice) => ({
    ...jogador, patos: comPalpite && indice !== 2 ? 1 : 0,
  }))
  if (comPalpite) {
    base.rodada.palpites[0].jogador = base.jogadores[2]
    base.rodada.resultado_timeout.ultimo_palpite = base.rodada.palpites[0]
    base.rodada.resultado_timeout.autor_protegido = base.jogadores[2]
  }
  return base
}

test("timer deriva de termina_em, diminui e em zero aguarda o backend", async (t) => {
  const players = [participante(1, "Levi", true), participante(2, "Jorge"), participante(3, "Luana")]
  const agoraOriginal = Date.now
  let agora = Date.parse("2030-01-01T12:00:30Z")
  Date.now = () => agora
  t.after(() => { Date.now = agoraOriginal })
  const ativa = partidaNp5(players, 1, "EM_ANDAMENTO")
  ativa.rodada.iniciada_em = "2030-01-01T12:00:00Z"
  ativa.rodada.termina_em = "2030-01-01T12:02:00Z"
  const intervalos = []
  const ui = setup(t, async (url) => url.endsWith("/auth/me")
    ? response({ detail: "não autenticado" }, 401)
    : response({ sala: sala("K7M4QX", players, 7, "EM_PARTIDA"), participante: players[0], partida: ativa }), {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "host" } }) },
  })
  globalThis.window.setInterval = (callback) => { intervalos.push(callback); return intervalos.length }
  globalThis.window.clearInterval = () => {}
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes("1:30"))
  assert.ok(!ui.view().includes("resposta_numerica"))
  agora += 1000
  await act(async () => intervalos.at(-1)())
  assert.ok(ui.view().includes("1:29"))
  agora = Date.parse("2030-01-01T12:02:00Z")
  await act(async () => intervalos.at(-1)())
  assert.ok(ui.view().includes("0:00"))
  assert.ok(ui.view().includes("TEMPO ESGOTADO — confirmando resultado"))
  assert.ok(!ui.view().includes("Resposta correta"))
})

test("polling renderiza timeout com e sem palpite e mantém próxima rodada", async (t) => {
  const players = [participante(1, "Levi", true), participante(2, "Jorge"), participante(3, "Luana")]
  let partida = partidaTimeout(players, 1, true)
  const host = setup(t, async (url) => url.endsWith("/auth/me")
    ? response({ detail: "não autenticado" }, 401)
    : response({ sala: sala("K7M4QX", players, 9, "EM_PARTIDA"), participante: players[0], partida }), {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "host" } }) },
  })
  await host.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(host.view().includes("TEMPO ESGOTADO"))
  assert.ok(host.view().includes("Luana — 700 km"))
  assert.ok(host.view().includes("Os demais jogadores ativos receberam 1 pato"))
  assert.ok(host.view().includes("Explicação do timeout"))
  assert.ok(host.view().includes("Levi1 🦆"))
  assert.ok(host.button("PRÓXIMA RODADA"))
  await host.unmount()

  partida = partidaTimeout(players, 2, false)
  const guest = setup(t, async (url) => url.endsWith("/auth/me")
    ? response({ detail: "não autenticado" }, 401)
    : response({ sala: sala("K7M4QX", players, 10, "EM_PARTIDA"), participante: players[1], partida }), {
    path: "/nem-a-pato/sala/K7M4QX",
    stored: { "quizhub-nem-pato-sessoes": JSON.stringify({ K7M4QX: { codigo: "K7M4QX", token: "guest" } }) },
  })
  await guest.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(guest.view().includes("Ninguém enviou um palpite"))
  assert.ok(guest.view().includes("Nenhum pato foi aplicado"))
  assert.equal(guest.button("PRÓXIMA RODADA"), undefined)
  assert.ok(guest.view().includes("Aguardando o host iniciar a próxima rodada"))
})

function estadoFinal(players, patos, { abandonado = null, cancelada = false } = {}) {
  const jogadores = players.map((item, indice) => ({
    id: `j${indice + 1}`,
    nome: item.nome,
    ordem_circular: indice + 1,
    status: item.nome === abandonado ? 'ABANDONOU' : 'ATIVO',
    eh_eu: indice === 0,
    patos: patos[indice],
  }))
  const ativos = jogadores.filter((jogador) => jogador.status === 'ATIVO')
  const menor = Math.min(...ativos.map((jogador) => jogador.patos))
  const maior = Math.max(...ativos.map((jogador) => jogador.patos))
  return {
    sala: sala('K7M4QX', players, 22, 'ENCERRADA'),
    participante: players[0],
    partida: {
      id: 'partida-final', numero: 1,
      status: cancelada ? 'CANCELADA' : 'FINALIZADA',
      rodada_atual: cancelada ? 4 : 10, total_rodadas: 10,
      duracao_rodada_segundos: 120, jogadores, rodada: null,
      resultado_final: cancelada ? null : {
        vencedores: ativos.filter((jogador) => jogador.patos === menor),
        patos_da_partida: ativos.filter((jogador) => jogador.patos === maior),
        abandonados: jogadores.filter((jogador) => jogador.status === 'ABANDONOU'),
        empate_geral: menor === maior,
        rodadas_concluidas: 10,
      },
    },
  }
}

test('F5 reconstrói final, ordena patos e mantém polling para revanche', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const final = estadoFinal(players, [2, 6, 3])
  let intervalos = 0
  const ui = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(final), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host' } }) },
  })
  globalThis.window.setInterval = () => { intervalos += 1; return intervalos }
  globalThis.window.clearInterval = () => {}
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  const exibido = ui.view()
  assert.ok(exibido.includes('FIM DE JOGO'))
  assert.ok(exibido.includes('VENCEDORLevi2 patos'))
  assert.ok(exibido.includes('PATO DA PARTIDAJorge6 patos'))
  assert.ok(exibido.indexOf('Levi2 🦆') < exibido.indexOf('Luana3 🦆'))
  assert.ok(exibido.indexOf('Luana3 🦆') < exibido.indexOf('Jorge6 🦆'))
  assert.equal(intervalos, 1)
  assert.equal(ui.button('PRÓXIMA RODADA'), undefined)
  assert.equal(ui.button('Jogar novamente'), undefined)
  assert.ok(ui.button('VOLTAR AO INÍCIO'))
  await act(async () => ui.button('VOLTAR AO INÍCIO').props.onClick())
  assert.equal(JSON.parse(ui.storage.get('quizhub-nem-pato-sessoes')).K7M4QX, undefined)
})

test('sala encerrada sem partida terminal continua polling até resultado completo', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const final = estadoFinal(players, [2, 6, 3])
  const intermediario = {
    ...final,
    partida: {
      ...final.partida,
      status: 'EM_ANDAMENTO',
      resultado_final: null,
      rodada: { numero: 10, status: 'RESULTADO' },
    },
  }
  let consultas = 0
  const callbacks = new Map()
  const limpos = []
  let proximoIntervalo = 1
  const ui = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    consultas += 1
    return response(consultas === 1 ? intermediario : final)
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'guest' } }) },
  })
  globalThis.window.setInterval = (callback) => {
    const id = proximoIntervalo++
    callbacks.set(id, callback)
    return id
  }
  globalThis.window.clearInterval = (id) => {
    limpos.push(id)
    callbacks.delete(id)
  }
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('Sincronizando resultado final'))
  assert.ok(!ui.view().includes('FIM DE JOGO'))
  assert.equal(callbacks.size, 1)

  const polling = [...callbacks.values()][0]
  await act(async () => polling())
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('FIM DE JOGO'))
  assert.equal(consultas, 2)
  assert.equal(callbacks.size, 1)
  assert.equal(limpos.length, 0)
})

function estadoRevanche(players, eu = players[0]) {
  const jogadores = players.map((item, indice) => ({
    id: `r${indice + 1}`, nome: item.nome, ordem_circular: indice + 1,
    status: 'ATIVO', eh_eu: item.id === eu.id, patos: 0,
  }))
  return {
    sala: sala('K7M4QX', players, 23, 'EM_PARTIDA'),
    participante: eu,
    partida: {
      id: 'partida-2', numero: 2, status: 'EM_ANDAMENTO', rodada_atual: 0,
      total_rodadas: 10, duracao_rodada_segundos: 120, jogadores,
      resultado_final: null,
      rodada: {
        id: 21, numero: 1, status: 'AGUARDANDO_INICIO', pergunta: null,
        jogador_inicial: jogadores[0], jogador_da_vez: null, maior_palpite: null,
        palpites: [], iniciada_em: null, termina_em: null,
      },
    },
  }
}

test('host cria revanche com botão bloqueado e recebe partida 2 zerada', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const final = estadoFinal(players, [2, 6, 3])
  let resolver
  const ui = setup(t, async (url) => {
    if (url.endsWith('/auth/me')) return response({ detail: 'não autenticado' }, 401)
    if (url.endsWith('/jogar-novamente')) {
      return new Promise((resolve) => { resolver = () => resolve(response(estadoRevanche(players))) })
    }
    return response(final)
  }, {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host' } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.button('JOGAR NOVAMENTE'))
  let envio
  await act(async () => { envio = ui.button('JOGAR NOVAMENTE').props.onClick(); await Promise.resolve() })
  assert.equal(ui.button('Preparando revanche...').props.disabled, true)
  await act(async () => { resolver(); await envio })
  assert.ok(ui.view().includes('REVANCHE'))
  assert.ok(ui.view().includes('Partida 2'))
  assert.ok(ui.view().includes('Levi0 🦆'))
  assert.ok(ui.view().includes('Jorge0 🦆'))
  assert.ok(ui.view().includes('Luana0 🦆'))
  assert.ok(ui.button('Iniciar rodada'))
})

test('não-host aguarda e converge por polling para revanche sem F5', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const final = estadoFinal(players, [2, 6, 3])
  final.participante = players[1]
  let atual = final
  let polling
  const ui = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(atual), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'guest' } }) },
  })
  globalThis.window.setInterval = (callback) => { polling = callback; return 91 }
  globalThis.window.clearInterval = () => {}
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.equal(ui.button('JOGAR NOVAMENTE'), undefined)
  assert.ok(ui.view().includes('Esperando o host decidir se haverá revanche'))
  atual = estadoRevanche(players, players[1])
  await act(async () => polling())
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('Partida 2'))
  assert.ok(ui.view().includes('Aguardando o anfitrião iniciar a rodada'))
})

test('F5 recupera revanche preparada sem criar nova participação', async (t) => {
  const players = [participante(1, 'Levi', true), participante(2, 'Jorge'), participante(3, 'Luana')]
  const revanche = estadoRevanche(players, players[1])
  const ui = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(revanche), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'guest' } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('REVANCHE'))
  assert.ok(ui.view().includes('Partida 2'))
  assert.ok(ui.view().includes('Aguardando o anfitrião iniciar a rodada'))
})

test('tela final mostra empates e abandonados sem desempatar', async (t) => {
  const players = [participante(1, 'A', true), participante(2, 'B'), participante(3, 'C'), participante(4, 'D')]
  const empatado = estadoFinal(players, [1, 1, 5, 5])
  const ui = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(empatado), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host' } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('VENCEDORESA • B'))
  assert.ok(ui.view().includes('PATOS DA PARTIDAC • D'))
  await ui.unmount()

  const comAbandono = estadoFinal(players, [1, 2, 5, 0], { abandonado: 'D' })
  const recarregado = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(comAbandono), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host' } }) },
  })
  await recarregado.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(recarregado.view().includes('ABANDONARAMD — 0 patos'))
  assert.ok(recarregado.view().includes('VENCEDORA'))
})

test('empate geral e partida cancelada têm estados próprios', async (t) => {
  const players = [participante(1, 'A', true), participante(2, 'B'), participante(3, 'C')]
  let atual = estadoFinal(players, [3, 3, 3])
  const ui = setup(t, async (url) => url.endsWith('/auth/me')
    ? response({ detail: 'não autenticado' }, 401)
    : response(atual), {
    path: '/nem-a-pato/sala/K7M4QX',
    stored: { 'quizhub-nem-pato-sessoes': JSON.stringify({ K7M4QX: { codigo: 'K7M4QX', token: 'host' } }) },
  })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('EMPATE GERAL'))
  assert.ok(ui.view().includes('Todo mundo venceu. Todo mundo também virou Pato da Partida.'))
  await ui.unmount()

  atual = estadoFinal(players, [1, 2, 3], { cancelada: true })
  await ui.render()
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
  assert.ok(ui.view().includes('PARTIDA CANCELADA'))
  assert.ok(ui.view().includes('Não há jogadores ativos suficientes'))
  assert.ok(!ui.view().includes('PATO DA PARTIDA'))
  assert.equal(ui.button('JOGAR NOVAMENTE'), undefined)
  await act(async () => ui.button('VOLTAR AO INÍCIO').props.onClick())
  assert.ok(ui.view().includes('Criar sala'))
})
