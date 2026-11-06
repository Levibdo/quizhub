import { test, afterEach } from 'node:test'
import assert from 'node:assert/strict'

const fetchOriginal = globalThis.fetch
globalThis.window = { location: { protocol: 'http:', hostname: 'localhost' } }
const api = await import('../src/services/api.js')
const nemAPatoApi = await import('../src/services/nemAPato.js')
afterEach(() => { globalThis.fetch = fetchOriginal })

test('resolve URL da API em produção e desenvolvimento sem fallback público para 8001', () => {
  assert.equal(api.resolverApiUrl({
    producao: true,
    origem: 'https://quizhub.example',
  }), 'https://quizhub.example')
  assert.equal(api.resolverApiUrl({
    configurada: 'https://api.quizhub.example/',
    producao: true,
    origem: 'https://quizhub.example',
  }), 'https://api.quizhub.example')
  assert.equal(api.resolverApiUrl({
    producao: false,
    desenvolvimento: 'http://127.0.0.1:8001',
  }), 'http://127.0.0.1:8001')
  assert.throws(
    () => api.resolverApiUrl({ configurada: 'javascript:alert(1)', producao: true, origem: 'https://quizhub.example' }),
    /URL HTTP\(S\) válida/,
  )
})

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
  await api.criarPartida('Convidado', 'geral', '11111111-2222-4333-8444-555555555555')
  await api.enviarResposta('partida', 1, 2)
  assert.ok(chamadas.every((c) => c.credentials === 'include'))
  assert.equal(chamadas[0].url, 'http://127.0.0.1:8001/api/v1/auth/cadastro')
  assert.deepEqual(JSON.parse(chamadas[3].body), { categoria: 'geral' })
  assert.deepEqual(JSON.parse(chamadas[4].body), {
    jogador: 'Convidado', categoria: 'geral',
    visitante_id: '11111111-2222-4333-8444-555555555555',
  })
})

test('ranking global usa limite e filtro opcionais no endpoint público', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    return Response.json([])
  }
  await api.listarRanking()
  await api.listarRanking('geral', 10)
  assert.equal(chamadas[0].url, 'http://127.0.0.1:8001/api/v1/ranking?limit=10')
  assert.equal(chamadas[1].url, 'http://127.0.0.1:8001/api/v1/ranking?limit=10&categoria=geral')
  assert.ok(chamadas.every(({ opcoes }) => opcoes.method === 'GET' && opcoes.credentials === 'include'))
})

test('logout 204 não interpreta JSON', async () => {
  globalThis.fetch = async (_url, opcoes) => {
    assert.equal(opcoes.credentials, 'include')
    assert.equal(opcoes.method, 'POST')
    return { ok: true, status: 204, json() { throw new Error('não chamar') } }
  }
  assert.equal(await api.logout(), null)
})

test('resumo administrativo usa endpoint protegido com cookie', async () => {
  globalThis.fetch = async (url, opcoes) => {
    assert.equal(url, 'http://127.0.0.1:8001/api/v1/admin/resumo')
    assert.equal(opcoes.method, 'GET')
    assert.equal(opcoes.credentials, 'include')
    return Response.json({ catalogos: [], auditorias: [] })
  }
  assert.deepEqual(await api.obterResumoAdministrativo(), {
    catalogos: [], auditorias: [],
  })
})

test('dashboard administrativo usa endpoint somente de leitura com cookie', async () => {
  const dashboard = {
    indicadores: {
      usuarios: { total: 2, ativos: 1 },
      partidas: {
        total: 3, concluidas: 2,
        quiz_classico: { total: 2, concluidas: 1 },
        nem_a_pato: { total: 1, concluidas: 1 },
      },
      perguntas: { total: 500, oficiais: 500, privadas: 0 },
      categorias: { total: 5, oficiais: 5, privadas: 0 },
      catalogos_oficiais_ativos: 2,
    },
    temporada_ativa: null,
    catalogos: [],
    auditorias: [],
  }
  globalThis.fetch = async (url, opcoes) => {
    assert.equal(url, 'http://127.0.0.1:8001/api/v1/admin/dashboard')
    assert.equal(opcoes.method, 'GET')
    assert.equal(opcoes.credentials, 'include')
    assert.equal(opcoes.headers['X-CSRF-Token'], undefined)
    return Response.json(dashboard)
  }
  assert.deepEqual(await api.obterDashboardAdministrativo(), dashboard)
})

test('catálogos administrativos usam endpoint somente de leitura com cookie', async () => {
  const catalogos = { catalogos: [{ id: 'c1', catalogo_id: 'quiz_v2' }] }
  globalThis.fetch = async (url, opcoes) => {
    assert.equal(url, 'http://127.0.0.1:8001/api/v1/admin/catalogos')
    assert.equal(opcoes.method, 'GET')
    assert.equal(opcoes.credentials, 'include')
    assert.equal(opcoes.headers['X-CSRF-Token'], undefined)
    return Response.json(catalogos)
  }
  assert.deepEqual(await api.listarCatalogosOficiaisAdministrativos(), catalogos)
})

test('rascunhos oficiais integram revisão, idempotência, CSRF e preservam BIGINT como string', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) {
      return Response.json({ token: 'csrf-rascunho', expira_em_segundos: 1800 })
    }
    if (opcoes.method === 'GET') return Response.json({ itens: [], total: 0 })
    return Response.json({ id: 'p1', revisao: 3 })
  }
  await api.listarRascunhosOficiais({ modo: 'NEM_A_PATO', limite: 20 })
  await api.validarRascunhoOficial('r1')
  await api.salvarPerguntaRascunho('r1', 'p1', {
    id_editorial: 'MAC-999', categoria_id: 'cat-1', enunciado: 'Quantos?',
    explicacao: 'Explicação.', ativa: true, resposta_numerica: '9007199254740993',
    natureza_resposta: 'EXATA', referencias: [{ titulo: 'Fonte', url: 'https://example.org', acessada_em: '2026-10-22' }],
  }, 2, 'chave-idempotente')

  const consulta = new URL(chamadas[0].url)
  assert.equal(consulta.searchParams.get('modo'), 'NEM_A_PATO')
  assert.equal(chamadas[1].url, 'http://127.0.0.1:8001/api/v1/admin/catalogos/rascunhos/r1/validacao')
  assert.equal(chamadas[1].opcoes.headers['X-CSRF-Token'], undefined)
  const escrita = chamadas[3]
  assert.equal(escrita.opcoes.method, 'PUT')
  assert.equal(escrita.opcoes.headers['If-Match'], '"2"')
  assert.equal(escrita.opcoes.headers['Idempotency-Key'], 'chave-idempotente')
  assert.equal(escrita.opcoes.headers['X-CSRF-Token'], 'csrf-rascunho')
  assert.equal(JSON.parse(escrita.opcoes.body).resposta_numerica, '9007199254740993')
})

test('perguntas oficiais serializam filtros e consultam detalhe pelo modo', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/perguntas/opcoes')) {
      return Response.json({ catalogos: [], categorias: [] })
    }
    if (url.includes('/api/v1/admin/perguntas?')) {
      return Response.json({ itens: [], pagina: 2, limite: 20, total: 0, total_paginas: 0 })
    }
    return Response.json({ id: 7, modo: 'NEM_A_PATO' })
  }
  await api.obterOpcoesPerguntasOficiais()
  await api.listarPerguntasOficiais({ pagina: 2, modo: 'NEM_A_PATO', busca: 'morte', ativa: false, dificuldade: '' })
  await api.obterPerguntaOficial('NEM_A_PATO', 7)
  const lista = new URL(chamadas[1].url)
  assert.equal(lista.searchParams.get('pagina'), '2')
  assert.equal(lista.searchParams.get('modo'), 'NEM_A_PATO')
  assert.equal(lista.searchParams.get('busca'), 'morte')
  assert.equal(lista.searchParams.get('ativa'), 'false')
  assert.equal(lista.searchParams.has('dificuldade'), false)
  assert.equal(chamadas[2].url, 'http://127.0.0.1:8001/api/v1/admin/perguntas/NEM_A_PATO/7')
  assert.ok(chamadas.every(({ opcoes }) => opcoes.method === 'GET' && opcoes.credentials === 'include'))
})

test('auditoria administrativa serializa filtros e paginação em consulta GET', async () => {
  globalThis.fetch = async (url, opcoes) => {
    const recebida = new URL(url)
    assert.equal(recebida.pathname, '/api/v1/admin/auditorias')
    assert.equal(recebida.searchParams.get('pagina'), '2')
    assert.equal(recebida.searchParams.get('limite'), '50')
    assert.equal(recebida.searchParams.get('resultado'), 'SUCESSO')
    assert.equal(recebida.searchParams.get('busca'), 'catalogo-2')
    assert.equal(recebida.searchParams.has('operacao'), false)
    assert.equal(opcoes.method, 'GET')
    assert.equal(opcoes.credentials, 'include')
    assert.equal(opcoes.headers['X-CSRF-Token'], undefined)
    return Response.json({
      itens: [], pagina: 2, limite: 50, total: 0, total_paginas: 0,
    })
  }
  const resposta = await api.listarAuditoriasAdministrativas({
    pagina: 2, limite: 50, resultado: 'SUCESSO', busca: 'catalogo-2', operacao: '',
  })
  assert.equal(resposta.pagina, 2)
})

test('importador administrativo obtém e envia CSRF sem afetar importação privada', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) {
      return Response.json({ token: 'csrf-assinado', expira_em_segundos: 1800 })
    }
    return Response.json({ total: 1, criadas: 1, falhas: 0, erros: [] })
  }
  const oficial = new File(['xlsx'], 'oficial.xlsx')
  await api.importarPerguntasOficiaisLegado(oficial)
  assert.equal(chamadas.length, 2)
  assert.equal(chamadas[0].opcoes.method, 'GET')
  assert.equal(chamadas[0].opcoes.headers['X-CSRF-Token'], undefined)
  assert.equal(chamadas[1].opcoes.headers['X-CSRF-Token'], 'csrf-assinado')
  assert.equal(chamadas[1].opcoes.headers['Content-Type'], undefined)

  chamadas.length = 0
  await api.validarImportacaoMeuConteudo('QUIZ_CLASSICO', oficial)
  assert.equal(chamadas.length, 1)
  assert.equal(chamadas[0].opcoes.headers['X-CSRF-Token'], undefined)
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

test('importação privada valida e confirma reenviando o mesmo arquivo sem Content-Type manual', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    return Response.json(url.endsWith('/validar') ? { pode_confirmar: true } : { criadas: 1 })
  }
  const arquivo = new File(['[]'], 'perguntas.json', { type: 'application/json' })
  await api.validarImportacaoMeuConteudo('NEM_A_PATO', arquivo)
  await api.confirmarImportacaoMeuConteudo('token-secreto', arquivo)
  assert.equal(chamadas[0].opcoes.body.get('modo'), 'NEM_A_PATO')
  assert.equal(chamadas[0].opcoes.body.get('arquivo'), arquivo)
  assert.equal(chamadas[1].opcoes.body.get('token_preview'), 'token-secreto')
  assert.equal(chamadas[1].opcoes.body.get('arquivo'), arquivo)
  assert.ok(chamadas.every(({ opcoes }) => opcoes.credentials === 'include' && opcoes.headers['Content-Type'] === undefined))
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

test('preserva código e mensagem estruturada de catálogo inativo', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({
    detail: {
      codigo: 'CATALOGO_OFICIAL_INATIVO',
      mensagem: 'Este modo de jogo está temporariamente indisponível. Nenhum catálogo de perguntas está ativo.',
    },
  }), { status: 503, headers: { 'Content-Type': 'application/json' } })

  await assert.rejects(
    () => api.criarPartida('Visitante', 'geral'),
    (erro) => erro.status === 503 &&
      erro.codigo === 'CATALOGO_OFICIAL_INATIVO' &&
      erro.message.includes('temporariamente indisponível'),
  )
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
  assert.equal(chamada.url, 'http://127.0.0.1:8001/api/v1/partidas/partida-123/proxima')
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
  assert.equal(chamada.url, 'http://127.0.0.1:8001/api/v1/categorias')
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
  assert.equal(chamada.url, 'http://127.0.0.1:8001/api/v1/categorias/jogaveis')
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
  assert.equal(chamadas[0].url, 'http://127.0.0.1:8001/api/v1/nem-pato/salas')
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
  assert.equal(chamada.url, 'http://127.0.0.1:8001/api/v1/nem-pato/salas/K7M4QX/iniciar')
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
  assert.equal(chamadas[0].url, 'http://127.0.0.1:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/iniciar')
  assert.equal(chamadas[0].opcoes.method, 'POST')
  assert.equal(chamadas[0].opcoes.headers['X-Nem-Pato-Token'], 'token-host')
  assert.equal(chamadas[1].url, 'http://127.0.0.1:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/7/palpites')
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
  assert.equal(chamada.url, "http://127.0.0.1:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/7/desafiar")
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
  assert.equal(chamada.url, "http://127.0.0.1:8001/api/v1/nem-pato/salas/K7M4QX/rodadas/51/proxima")
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
  assert.equal(chamada.url, 'http://127.0.0.1:8001/api/v1/nem-pato/salas/K7M4QX/jogar-novamente')
  assert.equal(chamada.opcoes.method, 'POST')
  assert.equal(chamada.opcoes.headers['X-Nem-Pato-Token'], 'token-host')
  assert.equal(chamada.opcoes.body, undefined)
  assert.equal(resposta.partida.numero, 2)
})

test('decisão editorial envia CSRF, idempotência e as duas revisões', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) return Response.json({ token: 'csrf-editorial' })
    return Response.json({ estado: 'APROVADA', revisao_editorial: 8 })
  }
  await api.decidirPerguntaRevisao(
    'draft-1', 'question-1',
    { decisao: 'APROVADA', justificativa: 'Evidência documental suficiente.' },
    4, 7, 'idem-editorial',
  )
  assert.equal(chamadas.length, 2)
  assert.match(chamadas[1].url, /\/revisao\/perguntas\/question-1\/decisoes$/)
  assert.equal(chamadas[1].opcoes.headers['X-CSRF-Token'], 'csrf-editorial')
  assert.equal(chamadas[1].opcoes.headers['Idempotency-Key'], 'idem-editorial')
  assert.equal(chamadas[1].opcoes.headers['If-Match'], '"4"')
  assert.equal(chamadas[1].opcoes.headers['X-Editorial-Revision'], '7')
})

test('consulta avisos do ciclo e registra decisões e fontes pelos IDs persistidos', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) return Response.json({ token: 'csrf' })
    if (opcoes.method === 'GET') return Response.json({ itens: [{ id: 'warning-1' }], total: 1 })
    return Response.json({ revisao_editorial: 3 })
  }
  const avisos = await api.listarAvisosRevisao('draft-1', { estado: 'PENDENTE', severidade: 'AVISO' })
  assert.equal(avisos.itens[0].id, 'warning-1')
  await api.verificarFonteRevisao('draft-1', 'question-1', 47, {
    resultado: 'SUFICIENTE', evidencia_documental: 'Documento consultado.',
    relacao_com_resposta: 'Relação direta.', justificativa: null,
  }, 4, 1, 'fonte-idem')
  await api.decidirAvisoRevisao('draft-1', 'warning-1', {
    decisao: 'ACEITO', justificativa: 'Aviso analisado e aceito.',
  }, 4, 2, 'aviso-idem')
  assert.match(chamadas[0].url, /revisao\/avisos\?estado=PENDENTE&severidade=AVISO$/)
  assert.match(chamadas[2].url, /fontes\/47\/verificacoes$/)
  assert.match(chamadas[4].url, /avisos\/warning-1\/decisao$/)
  assert.equal(chamadas[2].opcoes.headers['X-Editorial-Revision'], '1')
  assert.equal(chamadas[4].opcoes.headers['X-Editorial-Revision'], '2')
})

test('publicação incremental envia justificativa, CSRF, revisão e idempotência', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) return Response.json({ token: 'csrf-publicacao' })
    return Response.json({ status: 'PUBLICADO', versao: 3, total_perguntas: 30 })
  }
  const resposta = await api.publicarRascunhoEditorial('draft-15', 'Quinze perguntas novas revisadas.', 7, 'publicar-15')
  assert.equal(resposta.total_perguntas, 30)
  assert.match(chamadas[1].url, /catalogos\/rascunhos\/draft-15\/publicar$/)
  assert.equal(chamadas[1].opcoes.headers['X-CSRF-Token'], 'csrf-publicacao')
  assert.equal(chamadas[1].opcoes.headers['If-Match'], '"7"')
  assert.equal(chamadas[1].opcoes.headers['Idempotency-Key'], 'publicar-15')
  assert.deepEqual(JSON.parse(chamadas[1].opcoes.body), { justificativa: 'Quinze perguntas novas revisadas.' })
})

test('reativação de catálogo envia versão ativa, CSRF e idempotência', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) return Response.json({ token: 'csrf-reativacao' })
    return Response.json({ status: 'ATIVO', versao: 1, perguntas_elegiveis: 15 })
  }
  const resposta = await api.reativarCatalogoOficial(
    'catalogo-arquivado', 'Retorno editorial da versão anterior.',
    'catalogo-ativo', 'reativar-chave',
  )
  assert.equal(resposta.perguntas_elegiveis, 15)
  assert.match(chamadas[1].url, /catalogos\/catalogo-arquivado\/reativar$/)
  assert.equal(chamadas[1].opcoes.headers['X-CSRF-Token'], 'csrf-reativacao')
  assert.equal(chamadas[1].opcoes.headers['If-Match'], '"catalogo-ativo"')
  assert.equal(chamadas[1].opcoes.headers['Idempotency-Key'], 'reativar-chave')
  assert.deepEqual(JSON.parse(chamadas[1].opcoes.body), { justificativa: 'Retorno editorial da versão anterior.' })
})

test('categoria de rascunho usa revisão, CSRF e idempotência', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) return Response.json({ token: 'csrf-categoria' })
    return Response.json({ categoria_id: 'cat-1', nome: 'História' }, { status: 201 })
  }
  await api.salvarCategoriaRascunho('draft-1', null, {
    slug: 'historia', nome: 'História', descricao: null, ativa: true,
  }, 3, 'categoria-chave')
  assert.match(chamadas[1].url, /catalogos\/rascunhos\/draft-1\/categorias$/)
  assert.equal(chamadas[1].opcoes.headers['X-CSRF-Token'], 'csrf-categoria')
  assert.equal(chamadas[1].opcoes.headers['If-Match'], '"3"')
  assert.equal(chamadas[1].opcoes.headers['Idempotency-Key'], 'categoria-chave')
})

test('remoção e restauração de categoria são escritas versionadas protegidas', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) return Response.json({ token: 'csrf-categoria' })
    return Response.json({ revisao: 5 })
  }
  await api.removerCategoriaRascunho('draft-1', 'cat-1', 3, 'remover-cat')
  await api.restaurarCategoriaRascunho('draft-1', 'cat-1', 4, 'restaurar-cat')
  assert.equal(chamadas[1].opcoes.method, 'DELETE')
  assert.equal(chamadas[1].opcoes.headers['If-Match'], '"3"')
  assert.equal(chamadas[1].opcoes.headers['Idempotency-Key'], 'remover-cat')
  assert.match(chamadas[3].url, /categorias\/cat-1\/restaurar$/)
  assert.equal(chamadas[3].opcoes.headers['X-CSRF-Token'], 'csrf-categoria')
  assert.equal(chamadas[3].opcoes.headers['If-Match'], '"4"')
})

test('confirmação de importação JSON nunca omite CSRF ou idempotência', async () => {
  const chamadas = []
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, opcoes })
    if (url.endsWith('/api/v1/admin/csrf')) return Response.json({ token: 'csrf-json' })
    return Response.json({ rascunho_id: 'draft-json', publicado: false }, { status: 201 })
  }
  const conteudo = { nome_rascunho: 'Lote', modo: 'NEM_A_PATO', categorias: [], perguntas_quiz: [], perguntas_nem_pato: [] }
  const resposta = await api.confirmarImportacaoCatalogoJson('catalog-1', conteudo, 'a'.repeat(64), 'json-chave')
  assert.equal(resposta.publicado, false)
  assert.match(chamadas[1].url, /importacoes\/json\/confirmar$/)
  assert.equal(chamadas[1].opcoes.headers['X-CSRF-Token'], 'csrf-json')
  assert.equal(chamadas[1].opcoes.headers['Idempotency-Key'], 'json-chave')
})
