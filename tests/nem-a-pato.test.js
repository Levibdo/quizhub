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

function sala(codigo, participantes, versao = 0) {
  return {
    codigo,
    status: 'AGUARDANDO',
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
