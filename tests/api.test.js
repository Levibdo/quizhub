import { test, afterEach } from 'node:test'
import assert from 'node:assert/strict'

const fetchOriginal = globalThis.fetch
globalThis.window = { location: { protocol: 'http:', hostname: 'localhost' } }
const api = await import('../src/services/api.js')
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
