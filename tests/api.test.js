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

test('Meu Conteúdo usa contratos reais, cookies e aceita 204', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (opcoes.method === 'DELETE') return new Response(null, { status: 204 })
    return Response.json({ modos: [] })
  }
  await api.obterResumoMeuConteudo()
  await api.listarCategoriasMeuConteudo('NEM_A_PATO')
  await api.criarCategoriaMeuConteudo({ nome: 'Cinema', descricao: null, modo: 'NEM_A_PATO' })
  await api.editarCategoriaMeuConteudo('categoria', { ativa: false })
  assert.equal(await api.excluirCategoriaMeuConteudo('categoria'), null)
  assert.ok(chamadas.every((item) => item.opcoes.credentials === 'include'))
  assert.ok(chamadas[1].url.endsWith('/api/v1/meu-conteudo/categorias?modo=NEM_A_PATO'))
  assert.deepEqual(JSON.parse(chamadas[2].opcoes.body), {
    nome: 'Cinema', descricao: null, modo: 'NEM_A_PATO',
  })
  assert.equal(chamadas[3].opcoes.method, 'PATCH')
})

test('requisitar preserva detalhes 422 e deixa o navegador definir boundary de FormData', async () => {
  const formulario = new FormData()
  formulario.append('modo', 'QUIZ_CLASSICO')
  globalThis.fetch = async (_url, opcoes) => {
    assert.equal(opcoes.headers['Content-Type'], undefined)
    return Response.json({ detail: [{ loc: ['body', 'nome'], msg: 'inválido' }] }, { status: 422 })
  }
  await assert.rejects(
    api.requisitar('/teste', { method: 'POST', body: formulario }),
    (erro) => erro.status === 422 && Array.isArray(erro.detail) && /nome válido/.test(erro.message),
  )
})

test('perguntas próprias usam endpoints, filtros e métodos dos dois modos', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (opcoes.method === 'DELETE') return new Response(null, { status: 204 })
    return Response.json([])
  }
  await api.listarPerguntasMeuConteudo('QUIZ_CLASSICO', { categoria_id: 'categoria', ativa: false, offset: 20, limit: 20 })
  await api.obterPerguntaMeuConteudo('QUIZ_CLASSICO', 12)
  await api.criarPerguntaMeuConteudo('QUIZ_CLASSICO', { enunciado: 'Pergunta' })
  await api.editarPerguntaMeuConteudo('QUIZ_CLASSICO', 12, { ativa: false })
  assert.equal(await api.excluirPerguntaMeuConteudo('QUIZ_CLASSICO', 12), null)
  assert.match(chamadas[0].url, /perguntas\/classico\?categoria_id=categoria&ativa=false&offset=20&limit=20$/)
  assert.ok(chamadas.every((item) => item.opcoes.credentials === 'include'))
  assert.deepEqual(chamadas.map((item) => item.opcoes.method), ['GET', 'GET', 'POST', 'PATCH', 'DELETE'])
})

test('BIGINT Nem a Pato é enviado e lido sem perda de precisão', async () => {
  const maximo = '9223372036854775807'
  let corpoEnviado
  globalThis.fetch = async (_url, opcoes) => {
    corpoEnviado = opcoes.body
    return new Response(`{"id":1,"categoria_id":"categoria","enunciado":"Distância?","resposta_numerica":${maximo},"unidade":null,"explicacao":"Fonte estável","fonte":null,"ativa":true,"criada_em":"2026-01-01T00:00:00Z","atualizada_em":"2026-01-01T00:00:00Z","excluida_em":null}`, {
      status: 201, headers: { 'Content-Type': 'application/json' },
    })
  }
  const criada = await api.criarPerguntaMeuConteudo('NEM_A_PATO', {
    categoria_id: 'categoria', enunciado: 'Distância?', resposta_numerica: maximo,
    unidade: null, explicacao: 'Fonte estável', fonte: null,
  })
  assert.match(corpoEnviado, new RegExp(`"resposta_numerica":${maximo}`))
  assert.ok(!corpoEnviado.includes(`"${maximo}"`))
  assert.equal(criada.resposta_numerica, maximo)
})

test('BIGINT preserva múltiplas respostas, edição e consulta sem alterar outros textos', async () => {
  const maximo = '9223372036854775807'
  const textoComNumero = `O valor citado é ${maximo}`
  const corpos = []
  globalThis.fetch = async (url, opcoes) => {
    if (opcoes.body) corpos.push(opcoes.body)
    const item = (id, numero) => `{"id":${id},"categoria_id":"categoria","enunciado":${JSON.stringify(textoComNumero)},"resposta_numerica":${numero},"unidade":null,"explicacao":${JSON.stringify(`Explicação ${textoComNumero}`)},"fonte":null,"ativa":true,"criada_em":"2026-01-01T00:00:00Z","atualizada_em":"2026-01-01T00:00:00Z","excluida_em":null}`
    const corpo = url.includes('?') ? `[${item(1, 0)},${item(2, maximo)}]` : item(2, maximo)
    return new Response(corpo, { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  const lista = await api.listarPerguntasMeuConteudo('NEM_A_PATO')
  const individual = await api.obterPerguntaMeuConteudo('NEM_A_PATO', 2)
  const editada = await api.editarPerguntaMeuConteudo('NEM_A_PATO', 2, {
    resposta_numerica: maximo, explicacao: textoComNumero,
  })
  assert.deepEqual(lista.map((item) => item.resposta_numerica), ['0', maximo])
  assert.equal(lista[1].enunciado, textoComNumero)
  assert.equal(lista[1].explicacao, `Explicação ${textoComNumero}`)
  assert.equal(individual.resposta_numerica, maximo)
  assert.equal(editada.resposta_numerica, maximo)
  assert.match(corpos[0], new RegExp(`"resposta_numerica":${maximo}`))
  assert.ok(corpos[0].includes(JSON.stringify(textoComNumero)))
})

test('serializador Nem a Pato normaliza zero e rejeita valores fora do contrato', () => {
  const chamada = (valor) => api.criarPerguntaMeuConteudo('NEM_A_PATO', { resposta_numerica: valor })
  for (const invalido of ['-1', '1.5', 'texto', '9223372036854775808']) assert.throws(() => chamada(invalido))
  let corpo
  globalThis.fetch = async (_url, opcoes) => {
    corpo = opcoes.body
    return new Response('{"resposta_numerica":0}', { status: 200 })
  }
  return chamada('000').then((resposta) => {
    assert.equal(corpo, '{"resposta_numerica":0}')
    assert.equal(resposta.resposta_numerica, '0')
  })
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

test('listar categorias jogáveis usa o catálogo com autenticação opcional', async () => {
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify([]), { status: 200 })
  }
  await api.listarCategoriasJogaveis()
  assert.equal(chamada.url, 'http://localhost:8001/api/v1/categorias/jogaveis')
  assert.equal(chamada.opcoes.method, 'GET')
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

test('iniciar rodada e enviar palpite usam endpoints NP5, token e idempotência', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    return new Response(JSON.stringify({ partida: { rodada: { id: 7 } } }), { status: 200 })
  }
  await nemAPatoApi.iniciarRodadaNemAPato('K7M4QX', 'token-host')
  await nemAPatoApi.enviarPalpiteNemAPato(
    'K7M4QX', 7, 'token-levi', 123, '11111111-1111-4111-8111-111111111111',
  )
  assert.equal(chamadas[0].url, 'http://localhost:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/iniciar')
  assert.equal(chamadas[0].opcoes.method, 'POST')
  assert.equal(chamadas[0].opcoes.headers['X-Nem-Pato-Token'], 'token-host')
  assert.equal(chamadas[1].url, 'http://localhost:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/7/palpites')
  assert.equal(chamadas[1].opcoes.headers['X-Nem-Pato-Token'], 'token-levi')
  assert.deepEqual(JSON.parse(chamadas[1].opcoes.body), {
    valor: 123,
    client_action_id: '11111111-1111-4111-8111-111111111111',
  })
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


test("desafio usa endpoint NP6, token e somente client_action_id", async () => {
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify({ partida: { rodada: { status: "RESULTADO" } } }), { status: 200 })
  }
  await nemAPatoApi.desafiarPalpiteNemAPato(
    "K7M4QX", 7, "token-luana", "22222222-2222-4222-8222-222222222222",
  )
  assert.equal(chamada.url, "http://localhost:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/7/desafiar")
  assert.equal(chamada.opcoes.method, "POST")
  assert.equal(chamada.opcoes.headers["X-Nem-Pato-Token"], "token-luana")
  assert.deepEqual(JSON.parse(chamada.opcoes.body), {
    client_action_id: "22222222-2222-4222-8222-222222222222",
  })
})


test("próxima rodada usa endpoint NP6B e token do host", async () => {
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify({ partida: { rodada: { numero: 2 } } }), { status: 200 })
  }
  await nemAPatoApi.iniciarProximaRodadaNemAPato("K7M4QX", 51, "token-host")
  assert.equal(chamada.url, "http://localhost:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/51/proxima")
  assert.equal(chamada.opcoes.method, "POST")
  assert.equal(chamada.opcoes.headers["X-Nem-Pato-Token"], "token-host")
  assert.equal(chamada.opcoes.body, undefined)
})

test('jogar novamente usa endpoint NP9 e credencial do host', async () => {
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify({ partida: { numero: 2 } }), { status: 200 })
  }
  const resposta = await nemAPatoApi.jogarNovamenteNemAPato('K7M4QX', 'token-host')
  assert.equal(chamada.url, 'http://localhost:8001/api/v1/nem-pato/salas/K7M4QX/jogar-novamente')
  assert.equal(chamada.opcoes.method, 'POST')
  assert.equal(chamada.opcoes.headers['X-Nem-Pato-Token'], 'token-host')
  assert.equal(chamada.opcoes.body, undefined)
  assert.equal(resposta.partida.numero, 2)
})
