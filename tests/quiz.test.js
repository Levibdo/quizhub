import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { rolldown } from 'rolldown'
import { createElement, act } from 'react'
import { create } from 'react-test-renderer'

const require = createRequire(import.meta.url)
globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.window = { location: { protocol: 'http:', hostname: 'localhost' } }

// Compila o App real para os testes Node existentes, sem servidor ou navegador.
const bundle = await rolldown({
  input: fileURLToPath(new URL('../src/App.jsx', import.meta.url)),
  platform: 'node',
  transform: { jsx: { runtime: 'automatic' } },
  plugins: [{
    name: 'recursos-testes',
    resolveId(source) {
      if (source === 'react' || source.startsWith('react/')) {
        return { id: pathToFileURL(require.resolve(source)).href, external: true }
      }
      if (/\.(css|png)$/.test(source)) return '\0recurso'
    },
    load(id) { if (id === '\0recurso') return 'export default ""' },
  }],
})
const { output } = await bundle.generate({ format: 'es' })
await bundle.close()
const { default: App } = await import(`data:text/javascript;base64,${globalThis.Buffer.from(output[0].code).toString('base64')}`)

function texto(node) {
  if (typeof node === 'string') return node
  return (node.children || []).map(texto).join('')
}

for (const modo of ['correta', 'incorreta', 'timeout', 'final']) {
  test(`fluxo real: ${modo}, explicacao, espera e transicao manual`, async (t) => {
    const fetchOriginal = globalThis.fetch
    const storageOriginal = globalThis.localStorage
    const storage = new Map()
    globalThis.localStorage = {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    }
    t.mock.timers.enable({ apis: ['setTimeout'] })
    const pergunta = { id: 31, pergunta: 'Pergunta respondida?', alternativas: ['A', 'B', 'C', 'D'] }
    const seguinte = { id: 88, pergunta: 'Proxima autorizada?', alternativas: ['E', 'F', 'G', 'H'] }
    const partida = {
      partida_id: 'partida-real', jogador: 'Jogador', categoria: 'geral',
      status: 'EM_ANDAMENTO', pontuacao: 0, acertos: 0, erros: 0, pergunta_atual: pergunta,
    }
    const resultado = {
      ...partida, status: modo === 'final' ? 'FINALIZADA' : 'EM_ANDAMENTO',
      pergunta_atual: null,
      correta: modo === 'timeout' ? null : modo !== 'incorreta',
      timeout: modo === 'timeout', alternativa_correta: 1,
      explicacao: 'Explicacao persistida e confirmada.', pontos_ganhos: 170,
      pontuacao: 1234, acertos: 7, erros: 3,
    }
    const chamadas = []
    let confirmarResposta
    let confirmarProxima
    globalThis.fetch = async (url, options) => {
      chamadas.push({ url, options })
      let value
      if (url.endsWith('/auth/me')) value = { nome: 'Jogador' }
      else if (url.endsWith('/categorias')) value = [
        { id: '40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb', slug: 'geral', nome: 'Geral', descricao: 'Conhecimentos gerais.', modo: 'QUIZ_CLASSICO' },
      ]
      else if (url.endsWith('/respostas')) value = await new Promise((resolve) => { confirmarResposta = () => resolve(resultado) })
      else if (url.endsWith('/proxima')) value = await new Promise((resolve) => {
        confirmarProxima = () => resolve({ ...partida, pontuacao: 1234, acertos: 7, erros: 3, pergunta_atual: seguinte })
      })
      else value = partida
      return new Response(JSON.stringify(value), { status: 200 })
    }
    let renderer
    t.after(async () => {
      if (renderer) await act(async () => renderer.unmount())
      globalThis.fetch = fetchOriginal
      globalThis.localStorage = storageOriginal
      t.mock.timers.reset()
    })
    await act(async () => { renderer = create(createElement(App)) })
    const botao = (label) => renderer.root.findAllByType('button').find((b) => texto(b) === label)
    const visivel = () => texto(renderer.root)
    await act(async () => botao('Jogar').props.onClick())
    await act(async () => renderer.root.findAllByType('button').find((b) => b.props.className === 'categoria-card').props.onClick())
    assert.ok(!visivel().includes(resultado.explicacao))
    assert.equal(botao('Próxima pergunta →'), undefined)
    const alternativas = () => renderer.root.findByProps({ className: 'alternativas' }).findAllByType('button')
    const barraTempo = () => renderer.root.findByProps({ 'aria-label': 'Tempo restante' })
    assert.equal(barraTempo().props.role, 'progressbar')
    assert.equal(barraTempo().props['aria-valuemin'], '0')
    assert.equal(barraTempo().props['aria-valuemax'], 15)
    assert.equal(barraTempo().props['aria-valuenow'], 15)
    assert.equal(renderer.root.findAllByProps({ className: 'answer-option__status' }).length, 0)
    assert.ok(alternativas().every((alternativa) => alternativa.props.className === ''))
    const responder = alternativas()[0].props.onClick
    if (modo === 'timeout') {
      for (let i = 0; i < 10; i++) await act(async () => t.mock.timers.tick(1000))
      assert.equal(barraTempo().props['aria-valuenow'], 5)
      assert.ok(barraTempo().props.className.includes('timer-bar--urgente'))
      for (let i = 0; i < 5; i++) await act(async () => t.mock.timers.tick(1000))
      await act(async () => t.mock.timers.tick(1))
    } else {
      await act(async () => { responder(); responder() })
    }
    assert.equal(chamadas.filter((c) => c.url.endsWith('/respostas')).length, 1)
    assert.ok(!visivel().includes(resultado.explicacao))
    assert.equal(botao('Próxima pergunta →'), undefined)
    await act(async () => confirmarResposta())
    assert.ok(visivel().includes(resultado.explicacao))
    assert.ok(visivel().includes(modo === 'timeout' ? 'Tempo esgotado' : modo === 'incorreta' ? 'Resposta incorreta' : 'Resposta correta'))
    assert.ok(visivel().includes('B — B'))
    assert.ok(visivel().includes('+170 pontos'))
    if (modo === 'timeout') {
      assert.ok(visivel().includes('Nenhuma resposta foi registrada.'))
      assert.ok(!visivel().includes('Resposta incorreta'))
    }
    assert.ok(alternativas().every((b) => b.props.disabled))
    assert.ok(renderer.root.findAllByProps({ className: 'answer-option__status' }).length >= 1)
    assert.equal(alternativas()[1].props.className, 'correta')
    if (modo === 'incorreta') assert.equal(alternativas()[0].props.className, 'errada')
    const congelado = renderer.root.findAllByType('span').find((s) => s.props.className?.startsWith('timer')).children.join('')
    await act(async () => { responder(); t.mock.timers.tick(60000) })
    assert.equal(chamadas.filter((c) => c.url.endsWith('/respostas')).length, 1)
    assert.ok(visivel().includes(pergunta.pergunta))
    assert.ok(visivel().includes(resultado.explicacao))
    assert.equal(renderer.root.findAllByType('span').find((s) => s.props.className?.startsWith('timer')).children.join(''), congelado)
    if (modo === 'final') {
      assert.equal(botao('Próxima pergunta →'), undefined)
      await act(async () => { const click = botao('Ver resultado →').props.onClick; click(); click() })
      assert.ok(visivel().includes('Teste concluído'))
      assert.ok(visivel().includes('Pontos1234'))
      assert.ok(visivel().includes('Acertos7'))
      assert.ok(visivel().includes('Erros3'))
      assert.ok(visivel().includes('70%'))
      assert.ok(visivel().includes('JogadorJogador'))
      assert.ok(visivel().includes('CategoriaGeral'))
      assert.ok(botao('Jogar novamente →'))
      assert.ok(botao('Ver ranking'))
      assert.ok(botao('Voltar ao início'))
      const ranking = JSON.parse(storage.get('quizhub-ranking'))
      assert.equal(ranking.length, 1)
      assert.equal(ranking[0].pontuacao, 1234)
      assert.equal(chamadas.filter((c) => c.url.endsWith('/proxima')).length, 0)
    } else {
      await act(async () => { const click = botao('Próxima pergunta →').props.onClick; click(); click() })
      assert.equal(botao('Preparando próxima...').props.disabled, true)
      assert.equal(chamadas.filter((c) => c.url.endsWith('/proxima')).length, 1)
      assert.ok(visivel().includes(resultado.explicacao))
      await act(async () => confirmarProxima())
      assert.ok(!visivel().includes(resultado.explicacao))
      assert.ok(!visivel().includes(pergunta.pergunta))
      assert.ok(visivel().includes(seguinte.pergunta))
      assert.ok(visivel().includes('15s'))
      assert.equal(botao('Próxima pergunta →'), undefined)
      assert.ok(alternativas().every((b) => !b.props.disabled))
    }
  })
}

test('categorias da API incluem categoria desconhecida com fallback e id correto', async (t) => {
  const fetchOriginal = globalThis.fetch
  const storageOriginal = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem: () => {} }
  let resolverCategorias
  const chamadas = []
  globalThis.fetch = async (url, options) => {
    chamadas.push({ url, options })
    if (url.endsWith('/auth/me')) {
      return new Response(JSON.stringify({ nome: 'Jogador' }), { status: 200 })
    }
    if (url.endsWith('/categorias')) {
      const categorias = await new Promise((resolve) => { resolverCategorias = resolve })
      return new Response(JSON.stringify(categorias), { status: 200 })
    }
    return new Response(JSON.stringify({
      partida_id: 'nova', jogador: 'Jogador', categoria: 'ciencias',
      status: 'EM_ANDAMENTO', pontuacao: 0, acertos: 0, erros: 0,
      pergunta_atual: { id: 1, pergunta: 'Ciência?', alternativas: ['A', 'B', 'C', 'D'] },
    }), { status: 200 })
  }
  let renderer
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount())
    globalThis.fetch = fetchOriginal
    globalThis.localStorage = storageOriginal
  })
  await act(async () => { renderer = create(createElement(App)) })
  const botao = (label) => renderer.root.findAllByType('button').find((b) => texto(b) === label)
  await act(async () => botao('Jogar').props.onClick())
  assert.ok(texto(renderer.root).includes('Carregando categorias...'))
  assert.equal(renderer.root.findAllByProps({ className: 'categoria-card' }).length, 0)
  await act(async () => resolverCategorias([
    { id: '11111111-1111-4111-8111-111111111111', slug: 'ciencias', nome: 'Ciências', descricao: 'Uma categoria dinâmica.', modo: 'QUIZ_CLASSICO' },
  ]))
  assert.ok(texto(renderer.root).includes('Ciências'))
  assert.equal(
    renderer.root.findByProps({
      className: 'category-symbol category-symbol--fallback',
    }).props['data-symbol'],
    'fallback',
  )
  await act(async () => renderer.root.findByProps({ className: 'categoria-card' }).props.onClick())
  const criacao = chamadas.find((item) => item.url.endsWith('/partidas'))
  assert.deepEqual(JSON.parse(criacao.options.body), { categoria: 'ciencias' })
})

test('erro ao carregar categorias permite tentar novamente', async (t) => {
  const fetchOriginal = globalThis.fetch
  const storageOriginal = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem: () => {} }
  let tentativas = 0
  globalThis.fetch = async (url) => {
    if (url.endsWith('/auth/me')) {
      return new Response(JSON.stringify({ nome: 'Jogador' }), { status: 200 })
    }
    if (url.endsWith('/categorias')) {
      tentativas += 1
      if (tentativas === 1) {
        return new Response(JSON.stringify({ detail: 'Falha temporária' }), { status: 503 })
      }
      return new Response(JSON.stringify([
        { id: '40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb', slug: 'geral', nome: 'Geral', descricao: 'Conhecimentos gerais.', modo: 'QUIZ_CLASSICO' },
      ]), { status: 200 })
    }
    throw new Error(`URL inesperada: ${url}`)
  }
  let renderer
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount())
    globalThis.fetch = fetchOriginal
    globalThis.localStorage = storageOriginal
  })
  await act(async () => { renderer = create(createElement(App)) })
  const botao = (label) => renderer.root.findAllByType('button').find((b) => texto(b) === label)
  await act(async () => botao('Jogar').props.onClick())
  assert.ok(texto(renderer.root).includes('Não foi possível carregar as categorias.'))
  assert.equal(renderer.root.findAllByProps({ className: 'categoria-card' }).length, 0)
  await act(async () => botao('Tentar novamente').props.onClick())
  assert.ok(texto(renderer.root).includes('Geral'))
  assert.equal(tentativas, 2)
})

test('lista vazia de categorias exibe estado vazio sem permitir partida', async (t) => {
  const fetchOriginal = globalThis.fetch
  const storageOriginal = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem: () => {} }
  const chamadas = []
  globalThis.fetch = async (url, options) => {
    chamadas.push({ url, options })
    if (url.endsWith('/auth/me')) {
      return new Response(JSON.stringify({ nome: 'Jogador' }), { status: 200 })
    }
    if (url.endsWith('/categorias')) {
      return new Response(JSON.stringify([]), { status: 200 })
    }
    throw new Error(`URL inesperada: ${url}`)
  }
  let renderer
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount())
    globalThis.fetch = fetchOriginal
    globalThis.localStorage = storageOriginal
  })

  await act(async () => { renderer = create(createElement(App)) })
  const botao = renderer.root.findAllByType('button').find((item) => texto(item) === 'Jogar')
  await act(async () => botao.props.onClick())

  assert.ok(texto(renderer.root).includes('Nenhuma categoria disponível.'))
  assert.equal(renderer.root.findAllByProps({ className: 'categoria-card' }).length, 0)
  assert.equal(chamadas.some((item) => item.url.endsWith('/partidas')), false)
})

test('ranking usa categorias dinâmicas e separa Todos da categoria geral', async (t) => {
  const fetchOriginal = globalThis.fetch
  const storageOriginal = globalThis.localStorage
  const registros = [
    { id: 1, jogador: 'Ana', categoria: 'geral', pontuacao: 900, acertos: 5, erros: 5 },
    { id: 2, jogador: 'Ana', categoria: 'macabro', pontuacao: 1800, acertos: 9, erros: 1 },
    { id: 3, jogador: 'Bia', categoria: 'entretenimento', pontuacao: 1200, acertos: 7, erros: 3 },
    { id: 4, jogador: 'Arquivo', categoria: 'removida', pontuacao: 1000, acertos: 6, erros: 4 },
  ]
  globalThis.localStorage = {
    getItem: (key) => key === 'quizhub-ranking' ? JSON.stringify(registros) : null,
    setItem: () => {},
  }
  globalThis.fetch = async (url) => {
    if (url.endsWith('/auth/me')) return new Response(JSON.stringify({ nome: 'Jogador' }), { status: 200 })
    if (url.endsWith('/categorias')) return new Response(JSON.stringify([
      { id: '40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb', slug: 'geral', nome: 'Geral', descricao: '', modo: 'QUIZ_CLASSICO' },
      { id: '2a01b416-ae0c-53b4-8081-b5f33230048c', slug: 'entretenimento', nome: 'Entretenimento', descricao: '', modo: 'QUIZ_CLASSICO' },
      { id: '11111111-1111-4111-8111-111111111111', slug: 'macabro', nome: 'Macabro', descricao: '', modo: 'QUIZ_CLASSICO' },
    ]), { status: 200 })
    throw new Error(`URL inesperada: ${url}`)
  }
  let renderer
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount())
    globalThis.fetch = fetchOriginal
    globalThis.localStorage = storageOriginal
  })

  await act(async () => { renderer = create(createElement(App)) })
  const botao = (label) => renderer.root.findAllByType('button').find((item) => texto(item) === label)
  await act(async () => botao('Ver ranking').props.onClick())

  assert.equal(botao('Todos').props['aria-pressed'], true)
  assert.equal(botao('Geral').props['aria-pressed'], false)
  assert.ok(botao('Entretenimento'))
  assert.ok(botao('Macabro'))
  assert.ok(texto(renderer.root).includes('Arquivo'))
  assert.equal(renderer.root.findAllByProps({ className: 'ranking-item' }).length, 3)

  await act(async () => botao('Geral').props.onClick())
  assert.equal(botao('Todos').props['aria-pressed'], false)
  assert.equal(botao('Geral').props['aria-pressed'], true)
  assert.ok(texto(renderer.root).includes('Ana'))
  assert.ok(!texto(renderer.root).includes('Arquivo'))
  assert.equal(renderer.root.findAllByProps({ className: 'ranking-item' }).length, 1)

  await act(async () => botao('Macabro').props.onClick())
  assert.ok(texto(renderer.root).includes('1.800'))
  assert.ok(texto(renderer.root).includes('9 acertos · Macabro'))
})

test('ranking vazio mantém filtros dinâmicos e ação para jogar', async (t) => {
  const fetchOriginal = globalThis.fetch
  const storageOriginal = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem: () => {} }
  globalThis.fetch = async (url) => {
    if (url.endsWith('/auth/me')) return new Response(JSON.stringify({ nome: 'Jogador' }), { status: 200 })
    if (url.endsWith('/categorias')) return new Response(JSON.stringify([
      { id: '40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb', slug: 'geral', nome: 'Geral', descricao: '', modo: 'QUIZ_CLASSICO' },
    ]), { status: 200 })
    throw new Error(`URL inesperada: ${url}`)
  }
  let renderer
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount())
    globalThis.fetch = fetchOriginal
    globalThis.localStorage = storageOriginal
  })

  await act(async () => { renderer = create(createElement(App)) })
  const botao = (label) => renderer.root.findAllByType('button').find((item) => texto(item) === label)
  await act(async () => botao('Ver ranking').props.onClick())
  assert.ok(texto(renderer.root).includes('Ranking vazio'))
  assert.ok(texto(renderer.root).includes('Ainda não existem resultados registrados neste dispositivo.'))
  assert.ok(botao('Jogar novamente →'))
  await act(async () => botao('Geral').props.onClick())
  assert.ok(texto(renderer.root).includes('Ainda não existem resultados em Geral.'))
})
