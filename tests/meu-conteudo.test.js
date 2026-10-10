import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { rolldown } from 'rolldown'
import { createElement, act } from 'react'
import { create } from 'react-test-renderer'

const require = createRequire(import.meta.url)
globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.window = {
  location: { protocol: 'http:', hostname: 'localhost', pathname: '/' },
  history: { pushState() {} },
  setTimeout, clearTimeout,
  addEventListener() {}, removeEventListener() {},
}

const bundle = await rolldown({
  input: fileURLToPath(new URL('../src/App.jsx', import.meta.url)),
  platform: 'node',
  transform: { jsx: { runtime: 'automatic' } },
  plugins: [{
    name: 'recursos-testes-meu-conteudo',
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
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  return (node.children || []).map(texto).join('')
}

async function setup(t, { autenticado = true, categorias = [], interceptar } = {}) {
  const fetchOriginal = globalThis.fetch
  const windowOriginal = globalThis.window
  const storageOriginal = globalThis.localStorage
  const chamadas = []
  let lista = [...categorias]
  let resumo = () => ({
    modos: ['QUIZ_CLASSICO', 'NEM_A_PATO'].map((modo) => ({
      modo,
      categorias: { usadas: lista.filter((item) => item.modo === modo).length, limite: 10 },
      perguntas: { usadas: modo === 'QUIZ_CLASSICO' ? 3 : 4, limite: 200 },
    })),
  })
  globalThis.window = {
    location: { protocol: 'http:', hostname: 'localhost', pathname: '/' },
    history: { pushState() {} },
    setTimeout, clearTimeout,
    addEventListener() {}, removeEventListener() {},
  }
  globalThis.localStorage = { getItem: () => null, setItem() {} }
  globalThis.fetch = async (url, opcoes = {}) => {
    chamadas.push({ url, opcoes })
    if (interceptar) {
      const resposta = await interceptar({ url, opcoes, chamadas, lista })
      if (resposta) return resposta
    }
    if (url.endsWith('/auth/me')) {
      return autenticado
        ? Response.json({ id: 'usuario', nome: 'Levi' })
        : Response.json({ detail: 'não autenticado' }, { status: 401 })
    }
    if (url.endsWith('/meu-conteudo/resumo')) return Response.json(resumo())
    if (url.includes('/meu-conteudo/categorias?')) {
      const modo = new URL(url).searchParams.get('modo')
      return Response.json(lista.filter((item) => item.modo === modo))
    }
    if (url.endsWith('/meu-conteudo/categorias') && opcoes.method === 'POST') {
      const dados = JSON.parse(opcoes.body)
      const nova = { id: `id-${lista.length + 1}`, slug: 'nova', ativa: true, excluida_em: null, ...dados }
      lista.push(nova)
      return Response.json(nova, { status: 201 })
    }
    const id = decodeURIComponent(url.split('/').at(-1))
    if (opcoes.method === 'PATCH') {
      const dados = JSON.parse(opcoes.body)
      lista = lista.map((item) => item.id === id ? { ...item, ...dados } : item)
      return Response.json(lista.find((item) => item.id === id))
    }
    if (opcoes.method === 'DELETE') {
      lista = lista.filter((item) => item.id !== id)
      return new Response(null, { status: 204 })
    }
    return Response.json({ detail: 'rota inesperada' }, { status: 500 })
  }

  let renderer
  await act(async () => { renderer = create(createElement(App)) })
  async function esperar() {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  }
  await esperar()
  const ui = {
    renderer,
    chamadas,
    texto: () => texto(renderer.root),
    button: (label) => renderer.root.findAllByType('button').find((item) => texto(item) === label),
    input: (id) => renderer.root.findByProps({ id }),
    esperar,
  }
  t.after(async () => {
    await act(async () => renderer.unmount())
    globalThis.fetch = fetchOriginal
    globalThis.window = windowOriginal
    globalThis.localStorage = storageOriginal
  })
  return ui
}

const categoriaClassica = {
  id: '11111111-1111-4111-8111-111111111111', slug: 'historia', nome: 'História',
  descricao: 'Eventos históricos', modo: 'QUIZ_CLASSICO', ativa: true, excluida_em: null,
}

test('Meu Conteúdo aparece somente autenticado e carrega resumo, lista e modos', async (t) => {
  const ui = await setup(t, { categorias: [categoriaClassica] })
  assert.ok(ui.button('Meu Conteúdo'))
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Meu Conteúdo/)
  assert.match(ui.texto(), /Categorias1 \/ 10/)
  assert.match(ui.texto(), /Perguntas3 \/ 200/)
  assert.match(ui.texto(), /História/)
  assert.match(ui.texto(), /Perguntas em breve/)
  await act(async () => ui.button('Nem a Pato').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Nenhuma categoria própria/)
  assert.match(ui.texto(), /Perguntas4 \/ 200/)
})

test('convidado não recebe entrada para Meu Conteúdo', async (t) => {
  const ui = await setup(t, { autenticado: false })
  assert.ok(!ui.button('Meu Conteúdo'))
  assert.ok(ui.button('Entrar'))
})

test('cadastro valida localmente, preserva formulário no conflito e bloqueia duplo envio', async (t) => {
  let resolver
  let posts = 0
  const ui = await setup(t, {
    interceptar: async ({ url, opcoes }) => {
      if (url.endsWith('/meu-conteudo/categorias') && opcoes.method === 'POST') {
        posts += 1
        return new Promise((resolve) => { resolver = resolve })
      }
    },
  })
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Nova categoria').props.onClick())
  const formulario = ui.renderer.root.findByProps({ 'aria-label': 'Nova categoria' })
  await act(async () => formulario.props.onSubmit({ preventDefault() {} }))
  assert.match(ui.texto(), /Informe o nome/)
  await act(async () => ui.input('content-category-name').props.onChange({ target: { value: 'Ciência' } }))
  await act(async () => { formulario.props.onSubmit({ preventDefault() {} }); formulario.props.onSubmit({ preventDefault() {} }) })
  assert.equal(posts, 1)
  await act(async () => resolver(Response.json({ detail: 'nome de categoria já utilizado' }, { status: 409 })))
  assert.match(ui.texto(), /nome de categoria já utilizado/)
  assert.equal(ui.input('content-category-name').props.value, 'Ciência')
})

test('cadastro atualiza lista e quota; quota cheia desabilita nova categoria', async (t) => {
  const ui = await setup(t)
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Nova categoria').props.onClick())
  await act(async () => ui.input('content-category-name').props.onChange({ target: { value: 'Ciência' } }))
  await act(async () => ui.renderer.root.findByProps({ 'aria-label': 'Nova categoria' }).props.onSubmit({ preventDefault() {} }))
  await ui.esperar()
  assert.match(ui.texto(), /Categoria criada/)
  assert.match(ui.texto(), /Ciência/)
  assert.match(ui.texto(), /Categorias1 \/ 10/)
})

test('quota de dez categorias desabilita novo cadastro no modo correspondente', async (t) => {
  const categorias = Array.from({ length: 10 }, (_, indice) => ({
    ...categoriaClassica, id: `categoria-${indice}`, slug: `categoria-${indice}`, nome: `Categoria ${indice + 1}`,
  }))
  const ui = await setup(t, { categorias })
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Categorias10 \/ 10/)
  assert.equal(ui.button('Nova categoria').props.disabled, true)
})

test('edição e ativação usam PATCH e atualizam a categoria', async (t) => {
  const ui = await setup(t, { categorias: [categoriaClassica] })
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Editar').props.onClick())
  await act(async () => ui.input('content-category-name').props.onChange({ target: { value: 'História Mundial' } }))
  await act(async () => ui.renderer.root.findByProps({ 'aria-label': 'Editar categoria' }).props.onSubmit({ preventDefault() {} }))
  await ui.esperar()
  assert.match(ui.texto(), /História Mundial/)
  await act(async () => ui.button('Desativar').props.onClick())
  await ui.esperar()
  assert.ok(ui.button('Ativar'))
  const patches = ui.chamadas.filter((item) => item.opcoes.method === 'PATCH')
  assert.equal(patches.length, 2)
  assert.deepEqual(JSON.parse(patches[1].opcoes.body), { ativa: false })
})

test('exclusão pode ser cancelada, confirmada e trata dependência', async (t) => {
  let bloquear = true
  const ui = await setup(t, {
    categorias: [categoriaClassica],
    interceptar: async ({ opcoes }) => {
      if (opcoes.method === 'DELETE' && bloquear) {
        bloquear = false
        return Response.json({ detail: 'categoria possui perguntas' }, { status: 409 })
      }
    },
  })
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Excluir').props.onClick({ currentTarget: { focus() {} } }))
  assert.ok(ui.renderer.root.findByProps({ role: 'dialog' }))
  await act(async () => ui.button('Cancelar').props.onClick())
  assert.match(ui.texto(), /História/)
  await act(async () => ui.button('Excluir').props.onClick({ currentTarget: { focus() {} } }))
  await act(async () => ui.button('Excluir categoria').props.onClick())
  assert.match(ui.texto(), /Exclua primeiro todas as perguntas/)
  await act(async () => ui.button('Excluir categoria').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Categoria excluída/)
  assert.match(ui.texto(), /Nenhuma categoria própria/)
})

test('401 dentro da área limpa a sessão e encaminha ao login', async (t) => {
  let expirar = false
  const ui = await setup(t, {
    interceptar: async ({ url }) => {
      if (expirar && url.endsWith('/meu-conteudo/resumo')) {
        return Response.json({ detail: 'sessão expirada' }, { status: 401 })
      }
    },
  })
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  expirar = true
  await act(async () => ui.button('Nem a Pato').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Sua sessão expirou/)
  assert.match(ui.texto(), /Entrar no QuizHub/)
})

test('resposta antiga de categorias não substitui o modo novo', async (t) => {
  let resolverClassico
  const ui = await setup(t, {
    interceptar: async ({ url }) => {
      if (url.includes('categorias?modo=QUIZ_CLASSICO')) {
        return new Promise((resolve) => { resolverClassico = resolve })
      }
    },
  })
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1)) })
  await act(async () => ui.button('Nem a Pato').props.onClick())
  await ui.esperar()
  await act(async () => resolverClassico(Response.json([categoriaClassica])))
  assert.match(ui.texto(), /Nenhuma categoria própria/)
  assert.doesNotMatch(ui.texto(), /Eventos históricos/)
})
