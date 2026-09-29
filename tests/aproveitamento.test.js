import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  calcularAproveitamento,
  formatarAproveitamento,
} from '../src/utils/aproveitamento.js'

const casos = [
  { acertos: 10, erros: 0, percentual: 100, exibicao: '100%' },
  { acertos: 8, erros: 2, percentual: 80, exibicao: '80%' },
  { acertos: 2, erros: 8, percentual: 20, exibicao: '20%' },
  { acertos: 0, erros: 10, percentual: 0, exibicao: '0%' },
  { acertos: 3, erros: 2, percentual: 60, exibicao: '60%' },
  { acertos: 0, erros: 0, percentual: 0, exibicao: '0%' },
]

for (const caso of casos) {
  test(`${caso.acertos} acertos e ${caso.erros} erros`, () => {
    assert.equal(
      calcularAproveitamento(caso.acertos, caso.erros),
      caso.percentual,
    )
    assert.equal(
      formatarAproveitamento(caso.acertos, caso.erros),
      caso.exibicao,
    )
  })
}

test('percentual decimal usa no máximo duas casas e vírgula', () => {
  assert.equal(formatarAproveitamento(2, 1), '66,67%')
})
