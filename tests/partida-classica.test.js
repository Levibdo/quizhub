import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CHAVE_PARTIDA_CLASSICA_ATIVA,
  limparPartidaClassicaAtiva,
  obterPartidaClassicaAtiva,
  partidaIdDaRota,
  partidaIdValido,
  salvarPartidaClassicaAtiva,
} from '../src/utils/partidaClassica.js'

const PARTIDA_ID = '123e4567-e89b-42d3-a456-426614174000'

function armazenamento() {
  const dados = new Map()
  return {
    dados,
    getItem: (chave) => dados.get(chave) ?? null,
    setItem: (chave, valor) => dados.set(chave, valor),
    removeItem: (chave) => dados.delete(chave),
  }
}

test('persiste somente o UUID da partida clássica ativa', () => {
  const storage = armazenamento()
  salvarPartidaClassicaAtiva(PARTIDA_ID.toUpperCase(), storage)
  assert.deepEqual([...storage.dados.entries()], [[
    CHAVE_PARTIDA_CLASSICA_ATIVA,
    PARTIDA_ID,
  ]])
  assert.equal(obterPartidaClassicaAtiva(storage), PARTIDA_ID)
  limparPartidaClassicaAtiva(storage)
  assert.equal(obterPartidaClassicaAtiva(storage), null)
})

test('rejeita identificadores públicos malformados e não os recupera da rota', () => {
  assert.equal(partidaIdValido('partida-publica'), false)
  assert.equal(partidaIdDaRota('/quiz/partida-publica'), null)
  assert.equal(partidaIdDaRota(`/quiz/${PARTIDA_ID}`), PARTIDA_ID)
  assert.throws(
    () => salvarPartidaClassicaAtiva('partida-publica', armazenamento()),
    /Identificador de partida inválido/,
  )
})
