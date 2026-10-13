import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  CHAVE_VISITANTE_ID,
  obterVisitanteId,
  visitanteIdValido,
} from '../src/utils/visitante.js'


function storageFalso(inicial = {}) {
  const dados = new Map(Object.entries(inicial))
  return {
    dados,
    getItem: (chave) => dados.get(chave) ?? null,
    setItem: (chave, valor) => dados.set(chave, valor),
  }
}

test('gera e persiste UUID v4 para um novo perfil visitante', () => {
  const storage = storageFalso()
  const uuid = '11111111-2222-4333-8444-555555555555'
  assert.equal(obterVisitanteId(storage, { randomUUID: () => uuid }), uuid)
  assert.equal(storage.dados.get(CHAVE_VISITANTE_ID), uuid)
  assert.equal(visitanteIdValido(uuid), true)
})

test('reutiliza o UUID ao trocar de nome ou iniciar novas partidas', () => {
  const uuid = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
  const storage = storageFalso({ [CHAVE_VISITANTE_ID]: uuid.toUpperCase() })
  let geracoes = 0
  const primeira = obterVisitanteId(storage, { randomUUID: () => { geracoes += 1; return crypto.randomUUID() } })
  const segunda = obterVisitanteId(storage, { randomUUID: () => { geracoes += 1; return crypto.randomUUID() } })
  assert.equal(primeira, uuid)
  assert.equal(segunda, uuid)
  assert.equal(geracoes, 0)
})

test('substitui valor local inválido por um novo UUID válido', () => {
  const storage = storageFalso({ [CHAVE_VISITANTE_ID]: 'corrompido' })
  const novo = '12345678-1234-4abc-9def-1234567890ab'
  assert.equal(obterVisitanteId(storage, { randomUUID: () => novo }), novo)
  assert.equal(storage.dados.get(CHAVE_VISITANTE_ID), novo)
})
