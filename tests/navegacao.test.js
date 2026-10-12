import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { rolldown } from 'rolldown'
import { createElement, act } from 'react'
import { create } from 'react-test-renderer'

const require = createRequire(import.meta.url)
globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.window = {
  location: { protocol: 'http:', hostname: 'localhost', pathname: '/' },
}

const bundle = await rolldown({
  input: fileURLToPath(new URL('../src/App.jsx', import.meta.url)), platform: 'node',
  transform: { jsx: { runtime: 'automatic' } },
  plugins: [{ name: 'recursos-navegacao', resolveId(source) { if (source === 'react' || source.startsWith('react/')) return { id: pathToFileURL(require.resolve(source)).href, external: true }; if (/\.(css|png)$/.test(source)) return '\0recurso' }, load(id) { if (id === '\0recurso') return 'export default ""' } }],
})
const { output } = await bundle.generate({ format: 'es' })
await bundle.close()
const { default: App } = await import(`data:text/javascript;base64,${Buffer.from(output[0].code).toString('base64')}`)

function texto(node) { return typeof node === 'string' ? node : (node.children || []).map(texto).join('') }

function ambienteHistorico(caminhoInicial = '/') {
  const ouvintes = new Set()
  const location = { protocol: 'http:', hostname: 'localhost', pathname: caminhoInicial }
  const entradas = [{ state: null, path: caminhoInicial }]
  let indice = 0
  const emitir = () => ouvintes.forEach((ouvinte) => ouvinte({ state: entradas[indice].state }))
  const history = {
    state: null,
    pushState(state, _title, path) { entradas.splice(indice + 1); entradas.push({ state, path }); indice += 1; this.state = state; location.pathname = path },
    replaceState(state, _title, path) { entradas[indice] = { state, path }; this.state = state; location.pathname = path },
    back() { if (indice > 0) { indice -= 1; this.state = entradas[indice].state; location.pathname = entradas[indice].path; emitir() } },
    forward() { if (indice + 1 < entradas.length) { indice += 1; this.state = entradas[indice].state; location.pathname = entradas[indice].path; emitir() } },
    go(delta) { const destino = Math.max(0, Math.min(entradas.length - 1, indice + delta)); if (destino !== indice) { indice = destino; this.state = entradas[indice].state; location.pathname = entradas[indice].path; emitir() } },
  }
  return { location, history, addEventListener(tipo, fn) { if (tipo === 'popstate') ouvintes.add(fn) }, removeEventListener(tipo, fn) { if (tipo === 'popstate') ouvintes.delete(fn) }, setTimeout, clearTimeout }
}

async function montar(t, { autenticado = true, categorias = [], partida = null, caminhoInicial = '/' } = {}) {
  const windowOriginal = globalThis.window
  const fetchOriginal = globalThis.fetch
  const storageOriginal = globalThis.localStorage
  const documentOriginal = globalThis.document
  const focos = []
  const atributosTitulo = []
  globalThis.window = ambienteHistorico(caminhoInicial)
  globalThis.document = { querySelector: () => ({ setAttribute(nome, valor) { atributosTitulo.push([nome, valor]) }, focus() { focos.push(globalThis.window.location.pathname) } }), getElementById: () => null }
  globalThis.localStorage = { getItem: () => null, setItem() {} }
  globalThis.fetch = async (url) => {
    if (url.endsWith('/auth/me')) return autenticado
      ? Response.json({ id: 'u1', nome: 'Levi' })
      : Response.json({ detail: 'Não autenticado' }, { status: 401 })
    if (url.endsWith('/auth/logout')) return new Response(null, { status: 204 })
    if (url.endsWith('/meu-conteudo/resumo')) return Response.json({ modos: ['QUIZ_CLASSICO', 'NEM_A_PATO'].map((modo) => ({ modo, categorias: { usadas: 0, limite: 10 }, perguntas: { usadas: 0, limite: 200 } })) })
    if (url.includes('/meu-conteudo/categorias?')) return Response.json([])
    if (url.endsWith('/categorias/jogaveis')) return Response.json(categorias)
    if (url.endsWith('/partidas') && partida) return Response.json(await partida)
    return Response.json({ detail: 'inesperado' }, { status: 500 })
  }
  let renderer
  await act(async () => { renderer = create(createElement(App)) })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  t.after(async () => { await act(async () => renderer.unmount()); globalThis.window = windowOriginal; globalThis.fetch = fetchOriginal; globalThis.localStorage = storageOriginal; globalThis.document = documentOriginal })
  return { renderer, focos, atributosTitulo, button(label) { return renderer.root.findAllByType('button').find((item) => texto(item) === label) }, texto() { return texto(renderer.root) } }
}

test('cabeçalho mostra a sessão autenticada sem duplicar o indicador na home', async (t) => {
  const ui = await montar(t)
  const indicadores = ui.renderer.root.findAllByProps({ className: 'site-session' })
  assert.equal(indicadores.length, 1)
  assert.match(texto(indicadores[0]), /Sessão ativaLevi/)
  assert.equal(ui.renderer.root.findAllByProps({ className: 'session-chip' }).length, 0)

  await act(async () => ui.button('Sair').props.onClick())
  assert.equal(ui.renderer.root.findAllByProps({ className: 'site-session' }).length, 0)
})

test('cabeçalho não mostra sessão para visitante ou jogador convidado', async (t) => {
  const ui = await montar(t, { autenticado: false })
  assert.equal(ui.renderer.root.findAllByProps({ className: 'site-session' }).length, 0)

  await act(async () => ui.button('Jogar').props.onClick())
  assert.equal(window.location.pathname, '/jogador')
  assert.equal(ui.renderer.root.findAllByProps({ className: 'site-session' }).length, 0)
})

test('Voltar e Avançar reproduzem login e cadastro e focam o título', async (t) => {
  const ui = await montar(t, { autenticado: false })
  await act(async () => ui.button('Entrar').props.onClick())
  await act(async () => ui.button('Criar conta').props.onClick())
  assert.equal(window.location.pathname, '/cadastro')
  await act(async () => window.history.back())
  assert.match(ui.texto(), /Entrar no QuizHub/)
  await act(async () => window.history.forward())
  assert.match(ui.texto(), /Criar sua conta/)
  assert.ok(ui.focos.includes('/login'))
  assert.ok(ui.focos.includes('/cadastro'))
  assert.ok(ui.atributosTitulo.some(([nome, valor]) => nome === 'tabindex' && valor === '-1'))
})

test('histórico respeita cancelamento e confirmação de formulário sujo', async (t) => {
  const ui = await montar(t)
  await act(async () => ui.button('Ver ranking').props.onClick())
  await act(async () => ui.button('Voltar ao início').props.onClick())
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  await act(async () => ui.button('Nova categoria').props.onClick({ currentTarget: { focus() {} } }))
  const nome = ui.renderer.root.findByProps({ id: 'content-category-name' })
  await act(async () => nome.props.onChange({ target: { value: 'Rascunho' } }))
  await act(async () => { window.history.back(); window.history.back() })
  assert.match(ui.texto(), /Descartar alterações/)
  await act(async () => ui.button('Continuar editando').props.onClick())
  assert.equal(window.location.pathname, '/meu-conteudo')
  assert.equal(ui.renderer.root.findByProps({ id: 'content-category-name' }).props.value, 'Rascunho')
  await act(async () => { window.history.back(); window.history.back() })
  await act(async () => ui.button('Descartar alterações').props.onClick())
  assert.equal(window.location.pathname, '/ranking')
  assert.match(ui.texto(), /Ranking/)
})

test('histórico protege partida clássica ativa ao voltar', async (t) => {
  const ui = await montar(t, {
    categorias: [{ id: 'cat', slug: 'geral', nome: 'Geral', descricao: '', modo: 'QUIZ_CLASSICO' }],
    partida: {
      partida_id: 'partida-historico', jogador: 'Levi', categoria: 'geral',
      status: 'EM_ANDAMENTO', pontuacao: 0, acertos: 0, erros: 0,
      pergunta_atual: { id: 1, pergunta: 'Pergunta preservada?', alternativas: ['A', 'B', 'C', 'D'] },
    },
  })
  await act(async () => ui.button('Jogar').props.onClick())
  await act(async () => ui.renderer.root.findByProps({ className: 'categoria-card' }).props.onClick())
  assert.equal(window.location.pathname, '/quiz')
  await act(async () => window.history.back())
  assert.ok(ui.button('Continuar jogando'))
  assert.match(ui.texto(), /Pergunta preservada/)
  await act(async () => ui.button('Continuar jogando').props.onClick())
  assert.equal(window.location.pathname, '/quiz')
  assert.match(ui.texto(), /Pergunta preservada/)
  await act(async () => window.history.back())
  await act(async () => ui.button('Abandonar partida').props.onClick())
  assert.equal(window.location.pathname, '/categorias')
  assert.doesNotMatch(ui.texto(), /Pergunta preservada/)
  await act(async () => window.history.forward())
  assert.equal(window.location.pathname, '/')
  assert.ok(ui.button('Jogar'))
})

test('histórico privado não reabre Meu Conteúdo após logout', async (t) => {
  const ui = await montar(t)
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  await act(async () => window.history.back())
  await act(async () => ui.button('Sair').props.onClick())
  await act(async () => window.history.forward())
  assert.equal(window.location.pathname, '/login')
  assert.match(ui.texto(), /Entrar no QuizHub/)
  assert.match(ui.texto(), /Entre para acessar seu conteúdo/)
})

test('resposta pendente não reabre Quiz Clássico após navegação pelo histórico', async (t) => {
  let concluirPartida
  const partidaPendente = new Promise((resolve) => { concluirPartida = resolve })
  const ui = await montar(t, {
    categorias: [{ id: 'cat', slug: 'geral', nome: 'Geral', descricao: '', modo: 'QUIZ_CLASSICO' }],
    partida: partidaPendente,
  })
  await act(async () => ui.button('Jogar').props.onClick())
  await act(async () => {
    ui.renderer.root.findByProps({ className: 'categoria-card' }).props.onClick()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  await act(async () => window.history.back())
  concluirPartida({
    partida_id: 'tardia', jogador: 'Levi', categoria: 'geral', status: 'EM_ANDAMENTO',
    pontuacao: 0, acertos: 0, erros: 0,
    pergunta_atual: { id: 1, pergunta: 'Não deve reaparecer', alternativas: ['A', 'B', 'C', 'D'] },
  })
  await act(async () => { await partidaPendente; await new Promise((resolve) => setTimeout(resolve, 0)) })
  assert.equal(window.location.pathname, '/')
  assert.ok(ui.button('Jogar'))
  assert.doesNotMatch(ui.texto(), /Não deve reaparecer/)
})

test('F5 em rota sem estado não reconstrói partida e conteúdo privado exige sessão', async (t) => {
  const quiz = await montar(t, { caminhoInicial: '/quiz' })
  assert.equal(window.location.pathname, '/')
  assert.ok(quiz.button('Jogar'))
})

test('URL direta de Meu Conteúdo sem sessão converge para login', async (t) => {
  const ui = await montar(t, { autenticado: false, caminhoInicial: '/meu-conteudo' })
  assert.equal(window.location.pathname, '/login')
  assert.match(ui.texto(), /Entrar no QuizHub/)
})
