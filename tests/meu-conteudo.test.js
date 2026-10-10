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

async function setup(t, { autenticado = true, categorias = [], perguntas = null, interceptar } = {}) {
  const fetchOriginal = globalThis.fetch
  const windowOriginal = globalThis.window
  const storageOriginal = globalThis.localStorage
  const chamadas = []
  let lista = [...categorias]
  let listaPerguntas = [...(perguntas ?? [])]
  let resumo = () => ({
    modos: ['QUIZ_CLASSICO', 'NEM_A_PATO'].map((modo) => ({
      modo,
      categorias: { usadas: lista.filter((item) => item.modo === modo).length, limite: 10 },
      perguntas: { usadas: perguntas === null ? (modo === 'QUIZ_CLASSICO' ? 3 : 4) : listaPerguntas.filter((item) => item.modo === modo).length, limite: 200 },
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
    if (url.includes('/meu-conteudo/perguntas/')) {
      const modo = url.includes('/classico') ? 'QUIZ_CLASSICO' : 'NEM_A_PATO'
      const base = url.match(/\/perguntas\/(classico|nem-a-pato)$/)
      const consulta = new URL(url)
      if (opcoes.method === 'GET') {
        let resultado = listaPerguntas.filter((item) => item.modo === modo)
        const categoria = consulta.searchParams.get('categoria_id')
        const ativa = consulta.searchParams.get('ativa')
        if (categoria) resultado = resultado.filter((item) => item.categoria_id === categoria)
        if (ativa !== null) resultado = resultado.filter((item) => item.ativa === (ativa === 'true'))
        const offset = Number(consulta.searchParams.get('offset') ?? 0)
        const limit = Number(consulta.searchParams.get('limit') ?? 20)
        return Response.json(resultado.slice(offset, offset + limit))
      }
      if (opcoes.method === 'POST' && base) {
        const dados = JSON.parse(opcoes.body)
        const nova = { id: listaPerguntas.length + 1, modo, ativa: true, excluida_em: null, ...dados }
        listaPerguntas.push(nova)
        return Response.json(nova, { status: 201 })
      }
      const id = Number(url.split('/').at(-1))
      if (opcoes.method === 'PATCH') {
        const dados = JSON.parse(opcoes.body)
        listaPerguntas = listaPerguntas.map((item) => item.id === id ? { ...item, ...dados } : item)
        return Response.json(listaPerguntas.find((item) => item.id === id))
      }
      if (opcoes.method === 'DELETE') {
        listaPerguntas = listaPerguntas.filter((item) => item.id !== id)
        return new Response(null, { status: 204 })
      }
    }
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
    field: (id) => renderer.root.findAll((node) => ['input', 'select', 'textarea'].includes(node.type) && node.props.id === id)[0],
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
  assert.ok(ui.button('Perguntas'))
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

const categoriaSecundaria = {
  ...categoriaClassica, id: '22222222-2222-4222-8222-222222222222', slug: 'ciencia', nome: 'Ciência',
}
const categoriaNemPato = {
  ...categoriaClassica, id: '33333333-3333-4333-8333-333333333333', slug: 'estimativas', nome: 'Estimativas', modo: 'NEM_A_PATO',
}
const perguntaClassica = {
  id: 1, modo: 'QUIZ_CLASSICO', categoria_id: categoriaClassica.id, enunciado: 'Quem chegou primeiro?',
  alternativa_a: 'A', alternativa_b: 'B', alternativa_c: 'C', alternativa_d: 'D',
  alternativa_correta: 'A', explicacao: 'Explicação', ativa: true, excluida_em: null,
}
const perguntaNemPato = {
  id: 2, modo: 'NEM_A_PATO', categoria_id: categoriaNemPato.id, enunciado: 'Quantos quilômetros?',
  resposta_numerica: '40075', unidade: 'km', explicacao: 'Circunferência equatorial', fonte: 'Institucional', ativa: true, excluida_em: null,
}

async function abrirPerguntas(ui) {
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Perguntas').props.onClick())
  await ui.esperar()
}

test('perguntas listam por modo, filtram categoria e estado e paginam sem inventar total', async (t) => {
  const perguntas = Array.from({ length: 22 }, (_, indice) => ({
    ...perguntaClassica, id: indice + 1, enunciado: `Pergunta clássica ${indice + 1}`,
    categoria_id: indice === 21 ? categoriaSecundaria.id : categoriaClassica.id,
    ativa: indice !== 20,
  })).concat(perguntaNemPato)
  const ui = await setup(t, { categorias: [categoriaClassica, categoriaSecundaria, categoriaNemPato], perguntas })
  await abrirPerguntas(ui)
  assert.match(ui.texto(), /Pergunta clássica 1/)
  assert.ok(ui.button('Carregar mais'))
  await act(async () => ui.button('Carregar mais').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Pergunta clássica 22/)
  await act(async () => ui.renderer.root.findByProps({ id: 'question-filter-category' }).props.onChange({ target: { value: categoriaSecundaria.id } }))
  await ui.esperar()
  assert.match(ui.texto(), /Pergunta clássica 22/)
  assert.doesNotMatch(ui.texto(), /Pergunta clássica 1(?:\D|$)/)
  await act(async () => ui.renderer.root.findByProps({ id: 'question-filter-active' }).props.onChange({ target: { value: 'false' } }))
  await ui.esperar()
  assert.match(ui.texto(), /Nenhuma pergunta encontrada/)
  await act(async () => ui.button('Nem a Pato').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Quantos quilômetros/)
  assert.doesNotMatch(ui.texto(), /Pergunta clássica/)
})

test('cadastro clássico valida quatro alternativas e cria pergunta sem duplo envio', async (t) => {
  const ui = await setup(t, { categorias: [categoriaClassica], perguntas: [] })
  await abrirPerguntas(ui)
  await act(async () => ui.button('Nova pergunta').props.onClick())
  const form = ui.renderer.root.findByProps({ 'aria-label': 'Nova pergunta clássica' })
  await act(async () => form.props.onSubmit({ preventDefault() {} }))
  assert.match(ui.texto(), /Campo obrigatório/)
  const preencher = async (id, value) => act(async () => ui.field(id).props.onChange({ target: { value } }))
  await preencher('question-statement', 'Qual é a resposta?')
  for (const letra of ['a', 'b', 'c', 'd']) await preencher(`question-alternative-${letra}`, `Alternativa ${letra.toUpperCase()}`)
  await preencher('question-correct', 'D')
  await preencher('question-explanation', 'Porque D é correta.')
  await act(async () => { form.props.onSubmit({ preventDefault() {} }); form.props.onSubmit({ preventDefault() {} }) })
  await ui.esperar()
  assert.equal(ui.chamadas.filter((item) => item.opcoes.method === 'POST' && item.url.includes('/perguntas/classico')).length, 1)
  assert.match(ui.texto(), /Pergunta criada/)
  assert.match(ui.texto(), /Qual é a resposta/)
})

test('Nem a Pato aceita zero e BIGINT máximo, mas rejeita fração e texto', async (t) => {
  const ui = await setup(t, { categorias: [categoriaNemPato], perguntas: [] })
  await act(async () => ui.button('Meu Conteúdo').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Nem a Pato').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Perguntas').props.onClick())
  await ui.esperar()
  await act(async () => ui.button('Nova pergunta').props.onClick())
  const form = ui.renderer.root.findByProps({ 'aria-label': 'Nova pergunta Nem a Pato' })
  const preencher = async (id, value) => act(async () => ui.field(id).props.onChange({ target: { value } }))
  await preencher('question-statement', 'Qual é o número?')
  await preencher('question-explanation', 'Resposta verificável.')
  for (const invalido of ['1.5', 'texto', '9223372036854775808']) {
    await preencher('question-number', invalido)
    await act(async () => form.props.onSubmit({ preventDefault() {} }))
    assert.match(ui.texto(), /Informe um inteiro entre/)
  }
  await preencher('question-number', '0')
  await act(async () => form.props.onSubmit({ preventDefault() {} }))
  await ui.esperar()
  const primeira = ui.chamadas.find((item) => item.opcoes.method === 'POST' && item.url.includes('/nem-a-pato'))
  assert.match(primeira.opcoes.body, /"resposta_numerica":0/)

  await act(async () => ui.button('Nova pergunta').props.onClick())
  const formMax = ui.renderer.root.findByProps({ 'aria-label': 'Nova pergunta Nem a Pato' })
  await preencher('question-statement', 'Qual é o máximo?')
  await preencher('question-explanation', 'Limite do contrato.')
  await preencher('question-number', '9223372036854775807')
  await act(async () => formMax.props.onSubmit({ preventDefault() {} }))
  await ui.esperar()
  const posts = ui.chamadas.filter((item) => item.opcoes.method === 'POST' && item.url.includes('/nem-a-pato'))
  assert.match(posts[1].opcoes.body, /"resposta_numerica":9223372036854775807/)
})

test('pergunta edita categoria, alterna estado e exclusão exige confirmação', async (t) => {
  const ui = await setup(t, { categorias: [categoriaClassica, categoriaSecundaria], perguntas: [perguntaClassica] })
  await abrirPerguntas(ui)
  await act(async () => ui.button('Editar').props.onClick())
  await act(async () => ui.field('question-category').props.onChange({ target: { value: categoriaSecundaria.id } }))
  await act(async () => ui.renderer.root.findByProps({ 'aria-label': 'Editar pergunta clássica' }).props.onSubmit({ preventDefault() {} }))
  await ui.esperar()
  assert.match(ui.texto(), /Ciência/)
  await act(async () => ui.button('Desativar').props.onClick())
  await ui.esperar()
  assert.ok(ui.button('Ativar'))
  await act(async () => ui.button('Excluir').props.onClick())
  assert.ok(ui.renderer.root.findByProps({ role: 'dialog' }))
  await act(async () => ui.button('Cancelar').props.onClick())
  assert.match(ui.texto(), /Quem chegou primeiro/)
  await act(async () => ui.button('Excluir').props.onClick())
  await act(async () => ui.button('Excluir pergunta').props.onClick())
  await ui.esperar()
  assert.match(ui.texto(), /Pergunta excluída/)
  assert.match(ui.texto(), /Nenhuma pergunta encontrada/)
})

test('quota 200 bloqueia cadastro', async (t) => {
  const perguntas = Array.from({ length: 200 }, (_, indice) => ({ ...perguntaClassica, id: indice + 1, enunciado: `Questão ${indice + 1}` }))
  const ui = await setup(t, { categorias: [categoriaClassica], perguntas })
  await abrirPerguntas(ui)
  assert.equal(ui.button('Nova pergunta').props.disabled, true)
})

test('reativação em categoria inativa trata 409 sem remover a pergunta', async (t) => {
  const categoriaInativa = { ...categoriaClassica, ativa: false }
  const perguntaInativa = { ...perguntaClassica, ativa: false }
  const ui = await setup(t, {
    categorias: [categoriaInativa], perguntas: [perguntaInativa],
    interceptar: async ({ url, opcoes }) => {
      if (url.includes('/perguntas/classico/1') && opcoes.method === 'PATCH' && JSON.parse(opcoes.body).ativa === true) {
        return Response.json({ detail: 'categoria precisa estar ativa e não excluída' }, { status: 409 })
      }
    },
  })
  await abrirPerguntas(ui)
  await act(async () => ui.button('Ativar').props.onClick())
  assert.match(ui.texto(), /categoria precisa estar ativa/)
  assert.match(ui.texto(), /Quem chegou primeiro/)
  assert.ok(ui.button('Ativar'))
})
