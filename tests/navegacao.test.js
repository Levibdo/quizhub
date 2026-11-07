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
  return { location, history, addEventListener(tipo, fn) { if (tipo === 'popstate') ouvintes.add(fn) }, removeEventListener(tipo, fn) { if (tipo === 'popstate') ouvintes.delete(fn) }, confirm: () => true, prompt: () => 'Rascunho editorial', setTimeout, clearTimeout }
}

async function montar(t, {
  autenticado = true, categorias = [], partida = null, caminhoInicial = '/',
  auditoria = null, catalogosAdmin = null, perguntasAdmin = null, rascunhoStatus = 'EM_EDICAO',
  partidaRecuperada = null, respostaPartida = null, avancoPartida = null,
  storageInicial = {},
} = {}) {
  const windowOriginal = globalThis.window
  const fetchOriginal = globalThis.fetch
  const storageOriginal = globalThis.localStorage
  const documentOriginal = globalThis.document
  const focos = []
  const atributosTitulo = []
  const requisicoes = []
  globalThis.window = ambienteHistorico(caminhoInicial)
  globalThis.document = { querySelector: () => ({ setAttribute(nome, valor) { atributosTitulo.push([nome, valor]) }, focus() { focos.push(globalThis.window.location.pathname) } }), getElementById: () => null }
  const storage = new Map(Object.entries(storageInicial))
  globalThis.localStorage = {
    getItem: (chave) => storage.get(chave) ?? null,
    setItem: (chave, valor) => storage.set(chave, String(valor)),
    removeItem: (chave) => storage.delete(chave),
  }
  globalThis.fetch = async (url, opcoes = {}) => {
    requisicoes.push({ url, opcoes })
    if (url.endsWith('/auth/me')) return autenticado
      ? Response.json(typeof autenticado === 'object' ? autenticado : { id: 'u1', nome: 'Levi', perfil: 'JOGADOR' })
      : Response.json({ detail: 'Não autenticado' }, { status: 401 })
    if (url.endsWith('/auth/login')) return Response.json({ id: 'u1', nome: 'Levi', perfil: 'JOGADOR' })
    if (url.endsWith('/auth/logout')) return new Response(null, { status: 204 })
    if (url.endsWith('/meu-conteudo/resumo')) return Response.json({ modos: ['QUIZ_CLASSICO', 'NEM_A_PATO'].map((modo) => ({ modo, categorias: { usadas: 0, limite: 10 }, perguntas: { usadas: 0, limite: 200 } })) })
    if (url.includes('/meu-conteudo/categorias?')) return Response.json([])
    if (url.endsWith('/categorias/jogaveis')) return Response.json(categorias)
    if (url.includes('/ranking?')) return Response.json([])
    if (/\/partidas\/[0-9a-f-]+$/.test(url) && (opcoes.method ?? 'GET') === 'GET') {
      const recuperacao = typeof partidaRecuperada === 'function'
        ? await partidaRecuperada()
        : await partidaRecuperada
      if (recuperacao instanceof Error) {
        return Response.json(
          { detail: recuperacao.message },
          { status: recuperacao.status ?? 503 },
        )
      }
      return Response.json(recuperacao)
    }
    if (url.endsWith('/respostas') && respostaPartida) {
      const resposta = typeof respostaPartida === 'function'
        ? await respostaPartida()
        : await respostaPartida
      if (resposta instanceof Error) {
        return Response.json({ detail: resposta.message }, { status: resposta.status ?? 500 })
      }
      return Response.json(resposta)
    }
    if (url.endsWith('/proxima') && avancoPartida) {
      const resposta = typeof avancoPartida === 'function'
        ? await avancoPartida()
        : await avancoPartida
      if (resposta instanceof Error) {
        return Response.json({ detail: resposta.message }, { status: resposta.status ?? 500 })
      }
      return Response.json(resposta)
    }
    if (url.endsWith('/admin/resumo')) return Response.json({ catalogos: [], auditorias: [] })
    if (url.endsWith('/admin/csrf')) return Response.json({ token: 'csrf-teste-administrativo' })
    if (/\/admin\/catalogos\/[^/]+\/reativar$/.test(url)) return Response.json({ status: 'ATIVO', versao: 1, perguntas_elegiveis: 15 })
    if (url.endsWith('/admin/dashboard')) {
      return Response.json({
      indicadores: {
        usuarios: { total: 2, ativos: 2 },
        partidas: {
          total: 7, concluidas: 5,
          quiz_classico: { total: 4, concluidas: 3 },
          nem_a_pato: { total: 3, concluidas: 2 },
        },
        perguntas: { total: 510, oficiais: 500, privadas: 10 },
        categorias: { total: 7, oficiais: 5, privadas: 2 },
        catalogos_oficiais_ativos: 2,
      },
      temporada_ativa: {
        id: 'temporada-1', numero: 1, nome: 'Temporada 1', status: 'ATIVA',
        inicia_em: '2026-01-01T00:00:00Z', encerra_em: null,
      },
        catalogos: [], auditorias: [],
      })
    }
    if (url.endsWith('/admin/catalogos')) {
      if (catalogosAdmin === 'pendente') return new Promise(() => {})
      if (catalogosAdmin instanceof Error) {
        return Response.json({ detail: catalogosAdmin.message }, { status: 503 })
      }
      return Response.json(catalogosAdmin || {
        catalogos: [{
          id: 'catalogo-1', catalogo_id: 'quiz_classico_v2',
          modo: 'QUIZ_CLASSICO', versao: 2, status_registro: 'ATIVO',
          estado_editorial: null, situacao_ativacao: 'ATIVO',
          quantidade_perguntas: 400, criado_em: '2026-10-01T12:00:00Z',
          ativado_em: '2026-10-02T12:00:00Z', arquivado_em: null,
        }],
      })
    }
    if (url.includes('/admin/catalogos/rascunhos?')) {
      return Response.json({
        itens: [{
          id: 'draft-1', catalogo_origem_id: 'catalogo-1', catalogo_id: 'quiz_classico_v2',
          modo: 'QUIZ_CLASSICO', versao_base: 2, numero_rascunho: 1,
          nome: 'Revisão editorial', status: rascunhoStatus, revisao: 4,
          criado_por_id: 'a1', modificado_por_id: 'a1',
          criado_em: '2026-10-21T12:00:00Z', atualizado_em: '2026-10-22T12:00:00Z',
          descartado_em: null, motivo_descarte: null, total_perguntas: 400,
          adicionadas: 1, modificadas: 2, removidas: 1,
        }], pagina: 1, limite: 100, total: 1, total_paginas: 1,
      })
    }
    if (url.endsWith('/admin/catalogos/rascunhos/draft-1/validacao')) {
      return Response.json({
        rascunho_id: 'draft-1', catalogo_origem_id: 'catalogo-1', catalogo_id: 'quiz_classico_v2',
        versao_base: 2, modo: 'QUIZ_CLASSICO', revisao_validada: 4,
        resumo: rascunhoStatus === 'APROVADO' ? { perguntas_examinadas: 30, perguntas_publicaveis: 30, perguntas_validas_estruturalmente: 30, perguntas_com_problemas: 0, erros: 0, avisos: 0, informacoes: 0 } : { perguntas_examinadas: 400, perguntas_publicaveis: 399, perguntas_validas_estruturalmente: 398, perguntas_com_problemas: 1, erros: 1, avisos: 1, informacoes: 1 },
        achados: [
          { codigo: 'ALTERNATIVAS_EQUIVALENTES', nivel: 'ERRO', pergunta_id: 'draft-question-1', id_editorial: 'GER-001', campo: 'alternativas', mensagem: 'As alternativas devem ser distintas.', recomendacao: 'Revisar alternativas.' },
          { codigo: 'EXPLICACAO_CURTA', nivel: 'AVISO', pergunta_id: 'draft-question-1', id_editorial: 'GER-001', campo: 'explicacao', mensagem: 'A explicação deve ser revisada.', recomendacao: 'Complementar a explicação.' },
          { codigo: 'PERGUNTA_REMOVIDA', nivel: 'INFORMACAO', pergunta_id: null, id_editorial: null, campo: null, mensagem: 'Uma pergunta foi removida.' },
        ],
      })
    }
    if (url.endsWith('/admin/catalogos/rascunhos/draft-1')) {
      return Response.json({
        id: 'draft-1', catalogo_origem_id: 'catalogo-1', catalogo_id: 'quiz_classico_v2',
        modo: 'QUIZ_CLASSICO', versao_base: 2, numero_rascunho: 1,
        nome: 'Revisão editorial', status: rascunhoStatus, revisao: 4,
        criado_por_id: 'a1', modificado_por_id: 'a1', criado_em: '2026-10-21T12:00:00Z',
        atualizado_em: '2026-10-22T12:00:00Z', descartado_em: null, motivo_descarte: null,
        total_perguntas: 400, adicionadas: 1, modificadas: 2, removidas: 1,
      })
    }
    if (url.endsWith('/admin/catalogos/rascunhos/draft-1/revisao')) return Response.json({ rascunho_id: 'draft-1', status: rascunhoStatus, revisao_conteudo: 4, ciclo_id: 'cycle-1', estado_ciclo: 'CONCLUIDO', revisao_editorial: 31, hash_validacao: 'a'.repeat(64), contagens: { APROVADA: 15 }, elegivel_aprovacao: true, impedimentos_aprovacao: [], exige_justificativa_autorrevisao: false })
    if (url.endsWith('/admin/catalogos/rascunhos/draft-1/categorias')) return Response.json([{ id: 'draft-category-1', categoria_id: 'cat-quiz', modo: 'QUIZ_CLASSICO', slug: 'geral', nome: 'Conhecimentos Gerais', descricao: null, ativa: true, tipo_alteracao: 'INALTERADA', revisao: 1 }])
    if (url.includes('/admin/catalogos/rascunhos/draft-1/revisao/perguntas?')) return Response.json({ ciclo_id: 'cycle-1', revisao_editorial: 31, itens: [], pagina: 1, limite: 20, total: 15 })
    if (url.includes('/admin/catalogos/rascunhos/draft-1/revisao/avisos?')) return Response.json({ ciclo_id: 'cycle-1', revisao_editorial: 31, itens: [], pagina: 1, limite: 100, total: 0, total_paginas: 0, total_pendencias: 0 })
    if (url.endsWith('/admin/catalogos/rascunhos/draft-1/publicar')) return Response.json({ rascunho_id: 'draft-1', status: 'PUBLICADO', catalogo_publicado_id: 'catalogo-3', catalogo_id: 'quiz_classico_v2', modo: 'QUIZ_CLASSICO', versao: 3, total_perguntas: 30 })
    if (url.includes('/admin/catalogos/rascunhos/draft-1/perguntas?')) {
      return Response.json({ itens: [{ id: 'draft-question-1', id_editorial: 'GER-001', categoria_id: 'cat-quiz', categoria_slug: 'geral', categoria_nome: 'Conhecimentos Gerais', ordem: 1, enunciado: 'Qual é a resposta clássica?', ativa: true, tipo_alteracao: 'MODIFICADA', revisao: 2, dificuldade: 'MEDIA' }], pagina: 1, limite: 20, total: 1, total_paginas: 1 })
    }
    if (url.endsWith('/admin/catalogos/rascunhos/draft-1/perguntas/draft-question-1')) {
      return Response.json({ id: 'draft-question-1', id_editorial: 'GER-001', categoria_id: 'cat-quiz', categoria_slug: 'geral', categoria_nome: 'Conhecimentos Gerais', ordem: 1, enunciado: 'Qual é a resposta clássica?', ativa: true, tipo_alteracao: 'MODIFICADA', revisao: 2, dificuldade: 'MEDIA', explicacao: 'Explicação verificável.', alternativas: ['A', 'B', 'C', 'D'], alternativa_correta: 2, referencias: [{ titulo: 'Fonte acadêmica', url: 'https://example.org/fonte', acessada_em: '2026-10-21' }] })
    }
    if (url.includes('/admin/catalogos/rascunhos/draft-1/alteracoes?')) {
      return Response.json({ itens: [{ id: 'change-1', tipo: 'EDICAO', id_editorial: 'GER-001', revisao_anterior: 3, revisao_nova: 4, ocorrida_em: '2026-10-22T12:00:00Z' }], pagina: 1, limite: 20, total: 1, total_paginas: 1 })
    }
    if (url.endsWith('/admin/perguntas/opcoes')) {
      return Response.json({
        catalogos: [
          { id: 'c-quiz', catalogo_id: 'quiz_classico_v2', versao: 2, status: 'ATIVO', modo: 'QUIZ_CLASSICO' },
          { id: 'c-nem', catalogo_id: 'nem_a_pato_v1', versao: 1, status: 'ATIVO', modo: 'NEM_A_PATO' },
        ],
        categorias: [
          { id: 'cat-quiz', slug: 'geral', nome: 'Conhecimentos Gerais', modo: 'QUIZ_CLASSICO' },
          { id: 'cat-nem', slug: 'macabro', nome: 'Macabro', modo: 'NEM_A_PATO' },
        ],
      })
    }
    if (url.includes('/admin/perguntas?')) {
      if (perguntasAdmin instanceof Error) return Response.json({ detail: perguntasAdmin.message }, { status: 503 })
      if (perguntasAdmin === 'pendente') return new Promise(() => {})
      return Response.json(perguntasAdmin || {
        itens: [
          { id: 1, id_editorial: 'GER-001', modo: 'QUIZ_CLASSICO', enunciado: 'Qual é a resposta clássica?', ativa: true, dificuldade: 'MEDIA', categoria: { id: 'cat-quiz', slug: 'geral', nome: 'Conhecimentos Gerais' }, catalogo: { id: 'c-quiz', catalogo_id: 'quiz_classico_v2', versao: 2, status: 'ATIVO' } },
          { id: 1, id_editorial: 'MAC-001', modo: 'NEM_A_PATO', enunciado: 'Quantos casos foram registrados?', ativa: true, dificuldade: null, categoria: { id: 'cat-nem', slug: 'macabro', nome: 'Macabro' }, catalogo: { id: 'c-nem', catalogo_id: 'nem_a_pato_v1', versao: 1, status: 'ATIVO' } },
        ],
        pagina: 1, limite: 20, total: 2, total_paginas: 1,
      })
    }
    if (url.endsWith('/admin/perguntas/QUIZ_CLASSICO/1')) {
      return Response.json({ id: 1, id_editorial: 'GER-001', modo: 'QUIZ_CLASSICO', enunciado: 'Qual é a resposta clássica?', ativa: true, dificuldade: 'MEDIA', categoria: { id: 'cat-quiz', slug: 'geral', nome: 'Conhecimentos Gerais' }, catalogo: { id: 'c-quiz', catalogo_id: 'quiz_classico_v2', versao: 2, status: 'ATIVO' }, explicacao: 'Explicação verificável.', alternativas: ['A', 'B', 'C', 'D'], alternativa_correta: 2, resposta_numerica: null, unidade: null, tema_editorial: null, natureza_resposta: null, qualificacao_estimativa: null, fonte_legada: null, referencias: [{ titulo: 'Fonte acadêmica', url: 'https://example.org/fonte', acessada_em: '2026-10-21' }] })
    }
    if (url.endsWith('/admin/perguntas/NEM_A_PATO/1')) {
      return Response.json({ id: 1, id_editorial: 'MAC-001', modo: 'NEM_A_PATO', enunciado: 'Quantos casos foram registrados?', ativa: true, dificuldade: null, categoria: { id: 'cat-nem', slug: 'macabro', nome: 'Macabro' }, catalogo: { id: 'c-nem', catalogo_id: 'nem_a_pato_v1', versao: 1, status: 'ATIVO' }, explicacao: 'Explicação numérica.', alternativas: null, alternativa_correta: null, resposta_numerica: '9007199254740993', unidade: 'casos', tema_editorial: 'História', natureza_resposta: 'EXATA', qualificacao_estimativa: null, fonte_legada: null, referencias: [] })
    }
    if (url.includes('/admin/auditorias?')) {
      if (auditoria instanceof Error) {
        return Response.json({ detail: auditoria.message }, { status: 503 })
      }
      return Response.json(auditoria || {
        itens: [{
          id: 'audit-1', administrador_id: 'a1', administrador_nome: 'Admin',
          ocorrida_em: '2026-10-20T12:00:00Z', operacao: 'IMPORTAR_PERGUNTAS',
          recurso_tipo: 'CATALOGO', recurso_id: 'quiz-v2', resultado: 'SUCESSO',
          catalogo_id: 'quiz_classico_v2', catalogo_versao: 2,
          detalhes: { criadas: 400 },
        }],
        pagina: 1, limite: 20, total: 1, total_paginas: 1,
      })
    }
    if (url.endsWith('/partidas') && partida) return Response.json(await partida)
    return Response.json({ detail: 'inesperado' }, { status: 500 })
  }
  let renderer
  await act(async () => { renderer = create(createElement(App)) })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  t.after(async () => { await act(async () => renderer.unmount()); globalThis.window = windowOriginal; globalThis.fetch = fetchOriginal; globalThis.localStorage = storageOriginal; globalThis.document = documentOriginal })
  return { renderer, focos, atributosTitulo, requisicoes, storage, button(label) { return renderer.root.findAllByType('button').find((item) => texto(item) === label) }, texto() { return texto(renderer.root) } }
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

  await act(async () => ui.button('Jogar como convidado').props.onClick())
  await act(async () => ui.button('Jogar').props.onClick())
  assert.equal(window.location.pathname, '/jogador')
  assert.equal(ui.renderer.root.findAllByProps({ className: 'site-session' }).length, 0)
})

test('menu global expõe navegação acessível e recolhe após a ação', async (t) => {
  const ui = await montar(t, { autenticado: false })
  const menu = ui.button('Menu')
  assert.equal(menu.props['aria-expanded'], false)
  assert.equal(menu.props['aria-controls'], 'site-navigation')

  await act(async () => menu.props.onClick())
  assert.equal(ui.button('Fechar').props['aria-expanded'], true)
  assert.ok(ui.button('Ranking'))
  assert.ok(ui.button('Entrar'))
  assert.ok(ui.button('Criar conta'))
  assert.equal(ui.button('Meu Conteúdo'), undefined)
  assert.equal(ui.button('Administração'), undefined)

  await act(async () => ui.button('Ranking').props.onClick())
  assert.equal(window.location.pathname, '/ranking')
  assert.ok(ui.button('Menu'))
})

test('recarregar a rota do ranking também restaura os filtros de categorias', async (t) => {
  const ui = await montar(t, {
    caminhoInicial: '/ranking',
    categorias: [{
      id: '40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb',
      slug: 'geral',
      nome: 'Geral',
      descricao: '',
      modo: 'QUIZ_CLASSICO',
      origem: 'OFICIAL',
    }],
  })

  assert.match(ui.texto(), /Ranking/)
  assert.ok(ui.button('Geral'))
  assert.doesNotMatch(ui.texto(), /Nenhuma categoria disponível para filtro/)
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
  await act(async () => ui.button('Ranking').props.onClick())
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
  const partidaId = '123e4567-e89b-42d3-a456-426614174010'
  const ui = await montar(t, {
    categorias: [{ id: 'cat', slug: 'geral', nome: 'Geral', descricao: '', modo: 'QUIZ_CLASSICO' }],
    partida: {
      partida_id: partidaId, jogador: 'Levi', categoria: 'geral',
      status: 'EM_ANDAMENTO', pontuacao: 0, acertos: 0, erros: 0,
      pergunta_atual: { id: 1, pergunta: 'Pergunta preservada?', alternativas: ['A', 'B', 'C', 'D'] },
    },
  })
  await act(async () => ui.button('Continuar para os jogos').props.onClick())
  await act(async () => ui.button('Jogar').props.onClick())
  await act(async () => ui.renderer.root.findByProps({ className: 'categoria-card' }).props.onClick())
  assert.equal(window.location.pathname, `/quiz/${partidaId}`)
  await act(async () => window.history.back())
  assert.ok(ui.button('Continuar jogando'))
  assert.match(ui.texto(), /Pergunta preservada/)
  await act(async () => ui.button('Continuar jogando').props.onClick())
  assert.equal(window.location.pathname, `/quiz/${partidaId}`)
  assert.match(ui.texto(), /Pergunta preservada/)
  await act(async () => window.history.back())
  await act(async () => ui.button('Abandonar partida').props.onClick())
  assert.equal(window.location.pathname, '/categorias')
  assert.doesNotMatch(ui.texto(), /Pergunta preservada/)
  await act(async () => window.history.forward())
  assert.equal(window.location.pathname, '/')
  assert.ok(ui.button('Continuar para os jogos'))
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
  await act(async () => ui.button('Continuar para os jogos').props.onClick())
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
  assert.equal(window.location.pathname, '/jogos')
  assert.ok(ui.button('Jogar'))
  assert.doesNotMatch(ui.texto(), /Não deve reaparecer/)
})

test('rota /quiz sem identificador retorna ao início sem criar partida', async (t) => {
  const quiz = await montar(t, { caminhoInicial: '/quiz' })
  assert.equal(window.location.pathname, '/')
  assert.ok(quiz.button('Continuar para os jogos'))
  assert.equal(quiz.requisicoes.filter(({ url, opcoes }) => url.endsWith('/partidas') && opcoes.method === 'POST').length, 0)
})

test('F5 recupera a mesma partida, ordem e prazo sem criar duplicata', async (t) => {
  const partidaId = '123e4567-e89b-42d3-a456-426614174000'
  const prazo = new Date(Date.now() + 12_000).toISOString()
  const quiz = await montar(t, {
    caminhoInicial: `/quiz/${partidaId}`,
    partidaRecuperada: {
      partida_id: partidaId, jogador: 'Levi', categoria: 'geral', status: 'EM_ANDAMENTO',
      iniciada_em: new Date().toISOString(), pergunta_disponibilizada_em: new Date().toISOString(),
      prazo_resposta_em: prazo, finalizada_em: null, pontuacao: 120, acertos: 1, erros: 0,
      fase: 'AGUARDANDO_RESPOSTA', ordem_atual: 2, total_perguntas: 10,
      resultado_ultima_resposta: null,
      pergunta_atual: { id: 2, pergunta: 'Questão recuperada?', alternativas: ['A', 'B', 'C', 'D'] },
    },
  })
  assert.equal(window.location.pathname, `/quiz/${partidaId}`)
  assert.match(quiz.texto(), /Questão recuperada/)
  assert.match(quiz.texto(), /02 \/ 10/)
  assert.equal(quiz.storage.get('quizhub-classic-active-partida'), partidaId)
  assert.equal(quiz.requisicoes.filter(({ url, opcoes }) => url.endsWith('/partidas') && opcoes.method === 'POST').length, 0)
})

test('F5 após resposta recupera o feedback e permite avançar', async (t) => {
  const partidaId = '123e4567-e89b-42d3-a456-426614174001'
  const quiz = await montar(t, {
    caminhoInicial: `/quiz/${partidaId}`,
    partidaRecuperada: {
      partida_id: partidaId, jogador: 'Levi', categoria: 'geral', status: 'EM_ANDAMENTO',
      iniciada_em: new Date().toISOString(), pergunta_disponibilizada_em: null,
      prazo_resposta_em: null, finalizada_em: null, pontuacao: 130, acertos: 1, erros: 0,
      fase: 'AGUARDANDO_AVANCO', ordem_atual: 1, total_perguntas: 10,
      pergunta_atual: { id: 1, pergunta: 'Questão já respondida?', alternativas: ['A', 'B', 'C', 'D'] },
      resultado_ultima_resposta: {
        pergunta_id: 1, alternativa_selecionada: 0, explicacao: 'Feedback preservado.',
        correta: true, alternativa_correta: 0, timeout: false, pontos_ganhos: 130,
      },
    },
  })
  assert.match(quiz.texto(), /Feedback preservado/)
  assert.ok(quiz.button('Próxima pergunta →'))
})

test('F5 após avanço confirmado com resposta HTTP perdida recupera a próxima questão', async (t) => {
  const partidaId = '123e4567-e89b-42d3-a456-426614174008'
  const quiz = await montar(t, {
    caminhoInicial: `/quiz/${partidaId}`,
    storageInicial: { 'quizhub-classic-active-partida': partidaId },
    partidaRecuperada: {
      partida_id: partidaId, jogador: 'Levi', categoria: 'geral', status: 'EM_ANDAMENTO',
      iniciada_em: new Date().toISOString(), pergunta_disponibilizada_em: new Date().toISOString(),
      prazo_resposta_em: new Date(Date.now() + 12_000).toISOString(), finalizada_em: null,
      pontuacao: 120, acertos: 1, erros: 0, fase: 'AGUARDANDO_RESPOSTA',
      ordem_atual: 2, total_perguntas: 10, resultado_ultima_resposta: null,
      pergunta_atual: { id: 2, pergunta: 'Questão após avanço confirmado?', alternativas: ['A', 'B', 'C', 'D'] },
    },
  })
  assert.match(quiz.texto(), /Questão após avanço confirmado/)
  assert.match(quiz.texto(), /02 \/ 10/)
  assert.equal(quiz.requisicoes.filter(({ url, opcoes }) => url.endsWith('/partidas') && opcoes.method === 'POST').length, 0)
})

test('falha temporária de rede permite recuperar a mesma partida sem POST', async (t) => {
  const partidaId = '123e4567-e89b-42d3-a456-426614174002'
  let tentativas = 0
  const quiz = await montar(t, {
    caminhoInicial: `/quiz/${partidaId}`,
    partidaRecuperada: () => {
      tentativas += 1
      if (tentativas === 1) return Object.assign(new Error('indisponível'), { status: 503 })
      return {
        partida_id: partidaId, jogador: 'Levi', categoria: 'geral', status: 'EM_ANDAMENTO',
        iniciada_em: new Date().toISOString(), pergunta_disponibilizada_em: new Date().toISOString(),
        prazo_resposta_em: new Date(Date.now() + 10_000).toISOString(), finalizada_em: null,
        pontuacao: 0, acertos: 0, erros: 0, fase: 'AGUARDANDO_RESPOSTA',
        ordem_atual: 1, total_perguntas: 10, resultado_ultima_resposta: null,
        pergunta_atual: { id: 1, pergunta: 'Rede recuperada?', alternativas: ['A', 'B', 'C', 'D'] },
      }
    },
  })
  assert.match(quiz.texto(), /Não foi possível recuperar a partida/)
  await act(async () => quiz.button('Tentar novamente').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(quiz.texto(), /Rede recuperada/)
  assert.equal(tentativas, 2)
  assert.equal(quiz.requisicoes.filter(({ url, opcoes }) => url.endsWith('/partidas') && opcoes.method === 'POST').length, 0)
})

test('HTTP 409 ao responder sincroniza feedback confirmado pelo servidor', async (t) => {
  const partidaId = '123e4567-e89b-42d3-a456-426614174003'
  let leituras = 0
  const base = {
    partida_id: partidaId, jogador: 'Levi', categoria: 'geral', status: 'EM_ANDAMENTO',
    iniciada_em: new Date().toISOString(), finalizada_em: null,
    pontuacao: 0, acertos: 0, erros: 0, ordem_atual: 1, total_perguntas: 10,
    pergunta_atual: { id: 1, pergunta: 'Resposta concorrente?', alternativas: ['A', 'B', 'C', 'D'] },
  }
  const quiz = await montar(t, {
    caminhoInicial: `/quiz/${partidaId}`,
    partidaRecuperada: () => {
      leituras += 1
      if (leituras === 1) return {
        ...base, fase: 'AGUARDANDO_RESPOSTA', resultado_ultima_resposta: null,
        pergunta_disponibilizada_em: new Date().toISOString(),
        prazo_resposta_em: new Date(Date.now() + 10_000).toISOString(),
      }
      return {
        ...base, fase: 'AGUARDANDO_AVANCO', pergunta_disponibilizada_em: null,
        prazo_resposta_em: null, pontuacao: 120, acertos: 1,
        resultado_ultima_resposta: {
          pergunta_id: 1, alternativa_selecionada: 0, explicacao: 'Resposta sincronizada.',
          correta: true, alternativa_correta: 0, timeout: false, pontos_ganhos: 120,
        },
      }
    },
    respostaPartida: Object.assign(new Error('pergunta já respondida'), { status: 409 }),
  })
  const alternativa = quiz.renderer.root.findByProps({ className: 'alternativas' }).findAllByType('button')[0]
  await act(async () => alternativa.props.onClick())
  assert.match(quiz.texto(), /Resposta sincronizada/)
  assert.equal(leituras, 2)
})

test('deep link alheio não apaga outra partida ativa armazenada', async (t) => {
  const ativa = '123e4567-e89b-42d3-a456-426614174004'
  const alheia = '123e4567-e89b-42d3-a456-426614174005'
  const erro = Object.assign(new Error('partida inexistente'), { status: 404 })
  const quiz = await montar(t, {
    caminhoInicial: `/quiz/${alheia}`,
    partidaRecuperada: erro,
    storageInicial: { 'quizhub-classic-active-partida': ativa },
  })
  assert.match(quiz.texto(), /inexistente ou inacessível/)
  assert.equal(quiz.storage.get('quizhub-classic-active-partida'), ativa)
})

test('partida finalizada reabre a tela de resultado', async (t) => {
  const finalId = '123e4567-e89b-42d3-a456-426614174006'
  const finalizada = await montar(t, {
    caminhoInicial: `/quiz/${finalId}`,
    partidaRecuperada: {
      partida_id: finalId, jogador: 'Levi', categoria: 'geral', status: 'FINALIZADA',
      iniciada_em: new Date().toISOString(), pergunta_disponibilizada_em: null,
      prazo_resposta_em: null, finalizada_em: new Date().toISOString(), pontuacao: 500,
      acertos: 5, erros: 5, fase: 'FINALIZADA', ordem_atual: 10,
      total_perguntas: 10, pergunta_atual: null, resultado_ultima_resposta: null,
    },
  })
  assert.equal(window.location.pathname, '/resultado')
  assert.match(finalizada.texto(), /Teste concluído/)
  assert.equal(finalizada.storage.has('quizhub-classic-active-partida'), false)
})

test('sessão expirada não cria uma partida substituta', async (t) => {
  const expiradaId = '123e4567-e89b-42d3-a456-426614174007'
  const erro = Object.assign(new Error('identidade expirada'), { status: 401 })
  const expirada = await montar(t, {
    caminhoInicial: `/quiz/${expiradaId}`,
    partidaRecuperada: erro,
  })
  assert.match(expirada.texto(), /identidade de visitante expirou/)
  assert.equal(expirada.requisicoes.filter(({ url, opcoes }) => url.endsWith('/partidas') && opcoes.method === 'POST').length, 0)
})

test('boas-vindas separa visitante e autenticado antes do menu de jogos', async (t) => {
  const visitante = await montar(t, { autenticado: false })
  assert.match(visitante.texto(), /Bem-vindo ao QuizHub/)
  assert.ok(visitante.button('Jogar como convidado'))
  assert.ok(visitante.button('Fazer login'))
  assert.equal(visitante.button('Jogar'), undefined)
  await act(async () => visitante.button('Jogar como convidado').props.onClick())
  assert.equal(window.location.pathname, '/jogos')
  assert.ok(visitante.button('Jogar'))
  assert.ok(visitante.button('Abrir Nem a Pato'))
})

test('cards dos modos expõem uma única ação semântica em toda a superfície', async (t) => {
  const ui = await montar(t, { autenticado: false })
  await act(async () => ui.button('Jogar como convidado').props.onClick())

  const cards = ui.renderer.root.findAll((node) => (
    node.type === 'article' && node.props.className?.includes('mode-card--')
  ))
  assert.equal(cards.length, 2)
  for (const card of cards) {
    const acoes = card.findAllByType('button')
    assert.equal(acoes.length, 1)
    assert.equal(acoes[0].props.type, 'button')
    assert.equal(acoes[0].props.className, 'mode-card__hit-area')
  }

  await act(async () => ui.button('Jogar').props.onClick())
  assert.equal(window.location.pathname, '/jogador')
  await act(async () => window.history.back())
  await act(async () => ui.button('Abrir Nem a Pato').props.onClick())
  assert.equal(window.location.pathname, '/nem-a-pato')
})

test('login iniciado na boas-vindas redireciona ao menu de jogos', async (t) => {
  const ui = await montar(t, { autenticado: false })
  await act(async () => ui.button('Fazer login').props.onClick())
  assert.equal(window.location.pathname, '/login')
  await act(async () => ui.renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.equal(window.location.pathname, '/jogos')
  assert.ok(ui.button('Jogar'))
})

test('usuário autenticado continua da boas-vindas para os jogos', async (t) => {
  const ui = await montar(t)
  assert.ok(ui.button('Continuar para os jogos'))
  assert.equal(ui.button('Jogar como convidado'), undefined)
  await act(async () => ui.button('Continuar para os jogos').props.onClick())
  assert.equal(window.location.pathname, '/jogos')
  assert.ok(ui.button('Jogar'))
})

test('URL direta de Meu Conteúdo sem sessão converge para login', async (t) => {
  const ui = await montar(t, { autenticado: false, caminhoInicial: '/meu-conteudo' })
  assert.equal(window.location.pathname, '/login')
  assert.match(ui.texto(), /Entrar no QuizHub/)
})

test('URL administrativa direciona visitante ao login administrativo', async (t) => {
  const ui = await montar(t, { autenticado: false, caminhoInicial: '/admin' })
  assert.equal(window.location.pathname, '/login')
  assert.match(ui.texto(), /Acesso administrativo/)
  assert.match(ui.texto(), /conta administrativa/)
})

test('jogador comum recebe acesso negado e não vê menu administrativo', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'u1', nome: 'Jogador', perfil: 'JOGADOR' },
    caminhoInicial: '/admin',
  })
  assert.equal(window.location.pathname, '/admin')
  assert.match(ui.texto(), /Acesso negado/)
  assert.equal(ui.button('Administração'), undefined)
})

test('administrador vê menu e acessa painel restrito', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' },
  })
  assert.ok(ui.button('Administração'))
  await act(async () => ui.button('Administração').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.equal(window.location.pathname, '/admin')
  assert.match(ui.texto(), /Visão geral/)
  assert.match(ui.texto(), /Partidas75 concluídas/)
  assert.match(ui.texto(), /Catálogos oficiais/)
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(ui.texto(), /quiz classico v2/)
  assert.match(ui.texto(), /Perguntas400/)
  assert.match(ui.texto(), /Não registrado separadamente/)
  assert.ok(ui.button('Atualizar catálogos'))
  assert.ok(ui.button('Temporadas'))
  await act(async () => ui.button('Temporadas').props.onClick())
  assert.match(ui.texto(), /Temporada 1/)
  await act(async () => ui.button('Usuários').props.onClick())
  assert.match(ui.texto(), /Inativos/)
  await act(async () => ui.button('Auditoria').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(ui.texto(), /Auditoria administrativa/)
  assert.match(ui.texto(), /IMPORTAR PERGUNTAS/)
  assert.ok(ui.button('Aplicar filtros'))
  assert.ok(ui.button('Limpar filtros'))
  assert.equal(ui.button('Anterior').props.disabled, true)
  assert.equal(ui.button('Próxima').props.disabled, true)
})

test('catálogos administrativos apresentam estado vazio e erro recuperável', async (t) => {
  const vazio = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' },
    caminhoInicial: '/admin', catalogosAdmin: { catalogos: [] },
  })
  await act(async () => vazio.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(vazio.texto(), /Nenhum catálogo oficial cadastrado/)
  assert.ok(vazio.button('Criar catálogo inicial Quiz Clássico'))
  assert.ok(vazio.button('Criar catálogo inicial Nem a Pato'))

  const falha = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' },
    caminhoInicial: '/admin', catalogosAdmin: new Error('indisponível'),
  })
  await act(async () => falha.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(falha.texto(), /Não foi possível carregar os catálogos/)
  assert.ok(falha.button('Tentar novamente'))
})

test('administrador cria catálogo inicial para cada modo ausente com CSRF e idempotência', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' },
    caminhoInicial: '/admin',
    catalogosAdmin: { catalogos: [{
      id: 'catalogo-classico', catalogo_id: 'quiz_classico_v2', modo: 'QUIZ_CLASSICO',
      versao: 2, status_registro: 'ATIVO', estado_editorial: null,
      quantidade_perguntas: 400, criado_em: '2026-10-01T00:00:00Z',
      ativado_em: '2026-10-01T00:00:00Z',
    }] },
  })
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.equal(ui.button('Criar catálogo inicial Quiz Clássico'), undefined)
  assert.ok(ui.button('Criar catálogo inicial Nem a Pato'))
  await act(async () => ui.button('Criar catálogo inicial Nem a Pato').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  const chamada = ui.requisicoes.find(({ url, opcoes }) => (
    url.endsWith('/admin/catalogos') && opcoes.method === 'POST'
  ))
  assert.ok(chamada)
  assert.equal(JSON.parse(chamada.opcoes.body).modo, 'NEM_A_PATO')
  assert.equal(chamada.opcoes.headers['X-CSRF-Token'], 'csrf-teste-administrativo')
  assert.ok(chamada.opcoes.headers['Idempotency-Key'])
})

test('catálogos administrativos anunciam o carregamento', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' },
    caminhoInicial: '/admin', catalogosAdmin: 'pendente',
  })
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  assert.match(ui.texto(), /Carregando catálogos oficiais/)
})

test('administrador confirma reativação apenas de versão arquivada elegível', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin',
    catalogosAdmin: { catalogos: [
      { id: 'catalogo-ativo', catalogo_id: 'nem_incremental', modo: 'NEM_A_PATO', versao: 2, status_registro: 'ATIVO', estado_editorial: null, situacao_ativacao: 'ATIVO', quantidade_perguntas: 30, criado_em: '2026-10-02T00:00:00Z', ativado_em: '2026-10-02T00:00:00Z', arquivado_em: null },
      { id: 'catalogo-arquivado', catalogo_id: 'nem_incremental', modo: 'NEM_A_PATO', versao: 1, status_registro: 'ARQUIVADO', estado_editorial: null, situacao_ativacao: 'INATIVO', quantidade_perguntas: 15, quantidade_elegivel_reativacao: 15, elegivel_reativacao: true, criado_em: '2026-10-01T00:00:00Z', ativado_em: '2026-10-01T00:00:00Z', arquivado_em: '2026-10-02T00:00:00Z' },
    ] },
  })
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.ok(ui.button('Reativar esta versão'))
  await act(async () => ui.button('Reativar esta versão').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  const chamada = ui.requisicoes.find(({ url }) => url.endsWith('/admin/catalogos/catalogo-arquivado/reativar'))
  assert.equal(chamada.opcoes.headers['If-Match'], '"catalogo-ativo"')
  assert.equal(chamada.opcoes.headers['X-CSRF-Token'], 'csrf-teste-administrativo')
})

test('administrador consulta rascunho, abre editor e histórico sem ação de publicação', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin',
  })
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  assert.match(ui.texto(), /RASCUNHOS — NÃO PUBLICADOS/)
  assert.match(ui.texto(), /Revisão editorial/)
  assert.ok(ui.button('Gerenciar rascunho'))
  await act(async () => ui.button('Gerenciar rascunho').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  assert.match(ui.texto(), /RASCUNHO — NÃO PUBLICADO/)
  assert.match(ui.texto(), /Qual é a resposta clássica/)
  await act(async () => ui.button('Editar').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  assert.match(ui.texto(), /Editar pergunta/)
  assert.equal(ui.renderer.root.findByProps({ id: 'draft-id_editorial' }).props.disabled, true)
  assert.ok(ui.button('Adicionar referência'))
  assert.equal(ui.button('Publicar'), undefined)
  await act(async () => ui.button('Cancelar').props.onClick())
  await act(async () => ui.button('Histórico editorial').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  assert.match(ui.texto(), /Revisão 3 → 4/)
})

test('formulário de rascunho sujo protege troca de seção administrativa', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin',
  })
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  await act(async () => ui.button('Gerenciar rascunho').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  await act(async () => ui.button('Editar').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  const enunciado = ui.renderer.root.findByProps({ id: 'draft-enunciado' })
  await act(async () => enunciado.props.onChange({ target: { value: 'Alteração ainda não salva' } }))

  globalThis.window.confirm = () => false
  await act(async () => ui.button('Perguntas oficiais').props.onClick())
  assert.match(ui.texto(), /Alterações não salvas/)
  assert.match(ui.texto(), /Editar pergunta/)

  globalThis.window.confirm = () => true
  await act(async () => ui.button('Perguntas oficiais').props.onClick())
  assert.match(ui.texto(), /Consulta somente leitura\. Nenhuma pergunta ou catálogo é alterado/)
})

test('administrador valida rascunho, filtra achados e abre pergunta afetada', async (t) => {
  const ui = await montar(t, { autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin' })
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  await act(async () => ui.button('Gerenciar rascunho').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  await act(async () => ui.button('Validar rascunho').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  assert.match(ui.texto(), /Relatório da revisão 4/)
  assert.match(ui.texto(), /ALTERNATIVAS_EQUIVALENTES/)
  assert.match(ui.texto(), /não confirma a exatidão factual/)
  await act(async () => ui.button('Avisos').props.onClick())
  assert.doesNotMatch(ui.texto(), /ALTERNATIVAS_EQUIVALENTES/)
  assert.match(ui.texto(), /EXPLICACAO_CURTA/)
  await act(async () => ui.button('Abrir pergunta').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  assert.match(ui.texto(), /Editar pergunta/)
})

test('administrador aprovado confirma publicação incremental antes de ativar', async (t) => {
  const ui = await montar(t, { autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin', rascunhoStatus: 'APROVADO' })
  await act(async () => ui.button('Catálogos oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  await act(async () => ui.button('Consultar rascunho').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  assert.match(ui.texto(), /Publicar nova versão oficial/)
  assert.match(ui.texto(), /Revisadas neste ciclo15/)
  const painel = ui.renderer.root.findByProps({ className: 'admin-publication' })
  const justificativa = painel.findByType('textarea')
  const confirmacao = painel.findAllByType('input').find((item) => item.props.type === 'checkbox')
  assert.equal(ui.button('Publicar e ativar nova versão').props.disabled, true)
  await act(async () => justificativa.props.onChange({ target: { value: 'Quinze perguntas novas revisadas e aprovadas.' } }))
  await act(async () => confirmacao.props.onChange({ target: { checked: true } }))
  assert.equal(ui.button('Publicar e ativar nova versão').props.disabled, false)
  await act(async () => ui.button('Publicar e ativar nova versão').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  const chamada = ui.requisicoes.find(({ url }) => url.endsWith('/admin/catalogos/rascunhos/draft-1/publicar'))
  assert.ok(chamada)
  assert.deepEqual(JSON.parse(chamada.opcoes.body), { justificativa: 'Quinze perguntas novas revisadas e aprovadas.' })
})

test('perguntas oficiais listam os dois modos, filtram e abrem detalhes', async (t) => {
  const ui = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin',
  })
  await act(async () => ui.button('Perguntas oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(ui.texto(), /Qual é a resposta clássica/)
  assert.match(ui.texto(), /Quantos casos foram registrados/)
  assert.match(ui.texto(), /2 resultados/)
  const botoesDetalhe = ui.renderer.root.findAllByType('button').filter((item) => texto(item) === 'Visualizar detalhes')
  assert.equal(botoesDetalhe.length, 2)
  await act(async () => botoesDetalhe[0].props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(ui.texto(), /Explicação verificável/)
  assert.match(ui.texto(), /Resposta correta/)
  assert.match(ui.texto(), /Fonte acadêmica/)
  assert.ok(ui.button('Fechar detalhes'))

  const modo = ui.renderer.root.findByProps({ name: 'modo' })
  await act(async () => modo.props.onChange({ target: { name: 'modo', value: 'NEM_A_PATO' } }))
  const formulario = ui.renderer.root.findByProps({ 'aria-label': 'Filtros de perguntas oficiais' })
  await act(async () => formulario.props.onSubmit({ preventDefault() {} }))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.ok(ui.button('Limpar filtros'))
})

test('perguntas oficiais apresentam carregamento, vazio e erro', async (t) => {
  const pendente = await montar(t, { autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin', perguntasAdmin: 'pendente' })
  await act(async () => pendente.button('Perguntas oficiais').props.onClick())
  assert.match(pendente.texto(), /Carregando perguntas oficiais/)

  const vazio = await montar(t, { autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin', perguntasAdmin: { itens: [], pagina: 1, limite: 20, total: 0, total_paginas: 0 } })
  await act(async () => vazio.button('Perguntas oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(vazio.texto(), /Nenhuma pergunta oficial corresponde/)

  const falha = await montar(t, { autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' }, caminhoInicial: '/admin', perguntasAdmin: new Error('indisponível') })
  await act(async () => falha.button('Perguntas oficiais').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(falha.texto(), /Não foi possível carregar as perguntas/)
  assert.ok(falha.button('Tentar novamente'))
})

test('auditoria administrativa apresenta estado vazio', async (t) => {
  const vazio = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' },
    caminhoInicial: '/admin',
    auditoria: { itens: [], pagina: 1, limite: 20, total: 0, total_paginas: 0 },
  })
  await act(async () => vazio.button('Auditoria').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(vazio.texto(), /Nenhum evento corresponde aos filtros informados/)
})

test('auditoria administrativa apresenta erro e nova tentativa', async (t) => {
  const falha = await montar(t, {
    autenticado: { id: 'a1', nome: 'Admin', perfil: 'ADMIN' },
    caminhoInicial: '/admin', auditoria: new Error('indisponível'),
  })
  await act(async () => falha.button('Auditoria').props.onClick())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  assert.match(falha.texto(), /Não foi possível carregar a auditoria/)
  assert.ok(falha.button('Tentar novamente'))
})
