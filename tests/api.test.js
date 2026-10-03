import { test, afterEach } from 'node:test'
import assert from 'node:assert/strict'

const fetchOriginal = globalThis.fetch
globalThis.window = { location: { protocol: 'http:', hostname: 'localhost' } }
const api = await import('../src/services/api.js')
const nemAPatoApi = await import('../src/services/nemAPato.js')
afterEach(() => { globalThis.fetch = fetchOriginal })

test('auth e partidas enviam cookies; autenticado omite apelido', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, ...opcoes })
    return new Response(JSON.stringify({ nome: 'Levi' }), { status: 200 })
  }
  await api.cadastrarUsuario('Levi', 'levi@example.com', 'senha-teste')
  await api.login('levi@example.com', 'senha-teste')
  await api.obterUsuarioAtual()
  await api.criarPartida(undefined, 'geral')
  await api.criarPartida('Convidado', 'geral')
  await api.enviarResposta('partida', 1, 2)
  assert.ok(chamadas.every((c) => c.credentials === 'include'))
  assert.equal(chamadas[0].url, 'http://localhost:8001/api/v1/auth/cadastro')
  assert.deepEqual(JSON.parse(chamadas[3].body), { categoria: 'geral' })
  assert.deepEqual(JSON.parse(chamadas[4].body), { jogador: 'Convidado', categoria: 'geral' })
})

test('logout 204 não interpreta JSON', async () => {
  globalThis.fetch = async (_url, opcoes) => {
    assert.equal(opcoes.credentials, 'include')
    assert.equal(opcoes.method, 'POST')
    return { ok: true, status: 204, json() { throw new Error('não chamar') } }
  }
  assert.equal(await api.logout(), null)
})

test('preserva status e detail textual', async () => {
  for (const status of [401, 409, 500]) {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Falha' }), { status })
    await assert.rejects(api.obterUsuarioAtual(), (e) => e.status === status && e.message === 'Falha')
  }
})

test('422 não expõe input ou mensagem bruta com senha', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: [
    { loc: ['body', 'senha'], input: 'segredo', msg: 'segredo' },
    { loc: ['body', 'email'], input: 'invalido' },
  ] }), { status: 422 })
  await assert.rejects(api.obterUsuarioAtual(), (e) =>
    e.status === 422 && !e.message.includes('segredo') && e.message.includes('e-mail'))
})

test('erro de rede e resposta não JSON têm mensagens úteis', async () => {
  globalThis.fetch = async () => { throw new TypeError('network') }
  await assert.rejects(api.obterUsuarioAtual(), /conectar ao servidor/)
  globalThis.fetch = async () => new Response('indisponível', { status: 503 })
  await assert.rejects(api.obterUsuarioAtual(), (e) => e.status === 503)
})

test('avançar pergunta usa o endpoint, partida e pergunta respondida corretos', async () => {
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify({
      partida_id: 'partida-123',
      pergunta_atual: { id: 22, pergunta: 'Pergunta 2', alternativas: ['A', 'B', 'C', 'D'] },
    }), { status: 200 })
  }
  const resultado = await api.avancarPergunta('partida-123', 11)
  assert.equal(chamada.url, 'http://localhost:8001/api/v1/partidas/partida-123/proxima')
  assert.equal(chamada.opcoes.method, 'POST')
  assert.deepEqual(JSON.parse(chamada.opcoes.body), { pergunta_id: 11 })
  assert.equal(resultado.pergunta_atual.id, 22)
})

test('listar categorias consulta o endpoint público', async () => {
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify([
      { id: 'geral', nome: 'Geral', descricao: 'Conhecimentos gerais.' },
    ]), { status: 200 })
  }
  const categorias = await api.listarCategorias()
  assert.equal(chamada.url, 'http://localhost:8001/api/v1/categorias')
  assert.equal(chamada.opcoes.method, 'GET')
  assert.equal(categorias[0].id, 'geral')
})

test('Nem a Pato envia token somente nos endpoints autenticados', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }
  await nemAPatoApi.criarSalaNemAPato('Levi')
  await nemAPatoApi.entrarSalaNemAPato('K7M4QX', 'Jorge')
  await nemAPatoApi.obterSalaNemAPato('K7M4QX')
  await nemAPatoApi.recuperarSalaNemAPato('K7M4QX', 'token-opaco')
  await nemAPatoApi.abandonarSalaNemAPato('K7M4QX', 'token-opaco')
  assert.equal(chamadas[0].url, 'http://localhost:8001/api/v1/nem-pato/salas')
  assert.deepEqual(JSON.parse(chamadas[0].opcoes.body), { nome: 'Levi' })
  assert.equal(chamadas[2].opcoes.headers['X-Nem-Pato-Token'], undefined)
  assert.equal(chamadas[3].opcoes.headers['X-Nem-Pato-Token'], 'token-opaco')
  assert.equal(chamadas[4].opcoes.headers['X-Nem-Pato-Token'], 'token-opaco')
  assert.ok(chamadas.every((chamada) => chamada.opcoes.credentials === 'include'))
})

test('iniciar partida usa endpoint próprio e credencial temporária', async () => {
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify({ partida: { numero: 1 } }), { status: 200 })
  }
  const resposta = await nemAPatoApi.iniciarPartidaNemAPato('K7M4QX', 'token-host')
  assert.equal(chamada.url, 'http://localhost:8001/api/v1/nem-pato/salas/K7M4QX/iniciar')
  assert.equal(chamada.opcoes.method, 'POST')
  assert.equal(chamada.opcoes.headers['X-Nem-Pato-Token'], 'token-host')
  assert.equal(chamada.opcoes.body, undefined)
  assert.deepEqual(resposta, { partida: { numero: 1 } })
})

test('sessões Nem a Pato usam namespace próprio e removem somente a sala pedida', async () => {
  const anterior = globalThis.localStorage
  const dados = new Map()
  globalThis.localStorage = {
    getItem: (chave) => dados.get(chave) ?? null,
    setItem: (chave, valor) => dados.set(chave, valor),
  }
  try {
    nemAPatoApi.salvarSessaoNemAPato(' k7m4qx ', 'secreto-a')
    nemAPatoApi.salvarSessaoNemAPato('ABC234', 'secreto-b')
    assert.deepEqual(nemAPatoApi.carregarSessaoNemAPato('K7M4QX'), {
      codigo: 'K7M4QX', token: 'secreto-a',
    })
    assert.notEqual(nemAPatoApi.CHAVE_SESSOES, 'quizhub-ranking')
    nemAPatoApi.removerSessaoNemAPato('K7M4QX')
    assert.equal(nemAPatoApi.carregarSessaoNemAPato('K7M4QX'), null)
    assert.deepEqual(nemAPatoApi.carregarSessaoNemAPato('ABC234'), {
      codigo: 'ABC234', token: 'secreto-b',
    })
  } finally {
    globalThis.localStorage = anterior
  }
})
