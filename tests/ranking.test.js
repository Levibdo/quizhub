import { test } from 'node:test'
import assert from 'node:assert/strict'
import { classificarRanking } from '../src/utils/ranking.js'

function resultado(id, jogador, categoria, pontuacao, acertos) {
  return { id, jogador, categoria, pontuacao, acertos, erros: 10 - acertos }
}

test('ranking global mantém somente o melhor resultado por jogador sem somar partidas', () => {
  const ranking = classificarRanking([
    resultado(1, 'Ana', 'geral', 900, 5),
    resultado(2, 'Ana', 'tecnologia', 1200, 7),
    resultado(3, 'Bia', 'geral', 1100, 8),
  ])

  assert.deepEqual(ranking.map((item) => [item.jogador, item.pontuacao]), [
    ['Ana', 1200],
    ['Bia', 1100],
  ])
})

test('filtro de categoria é aplicado antes da seleção do melhor resultado', () => {
  const registros = [
    resultado(1, 'Ana', 'geral', 800, 5),
    resultado(2, 'Ana', 'tecnologia', 1800, 9),
    resultado(3, 'Bia', 'tecnologia', 900, 6),
  ]

  assert.deepEqual(classificarRanking(registros, 'geral').map((item) => item.id), [1])
  assert.deepEqual(classificarRanking(registros, 'tecnologia').map((item) => item.id), [2, 3])
})

test('ordena por pontuação, acertos e ID mais antigo, nesta ordem', () => {
  const ranking = classificarRanking([
    resultado(40, 'Quarta', 'geral', 1000, 7),
    resultado(30, 'Terceira', 'geral', 1100, 5),
    resultado(20, 'Segunda', 'geral', 1100, 8),
    resultado(10, 'Primeira', 'geral', 1100, 8),
  ])

  assert.deepEqual(ranking.map((item) => item.id), [10, 20, 30, 40])
})

test('ranking limita a classificação aos dez melhores jogadores', () => {
  const registros = Array.from({ length: 14 }, (_, indice) =>
    resultado(indice + 1, `Jogador ${indice + 1}`, 'geral', 2000 - indice, 8))

  const ranking = classificarRanking(registros)
  assert.equal(ranking.length, 10)
  assert.equal(ranking.at(-1).jogador, 'Jogador 10')
})

test('categoria histórica desconhecida permanece válida no ranking global', () => {
  const historico = resultado(1, 'Arquivo', 'categoria-removida', 1500, 8)

  assert.deepEqual(classificarRanking([historico]), [historico])
  assert.deepEqual(classificarRanking([historico], 'geral'), [])
})
