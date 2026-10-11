import assert from 'node:assert/strict'
import test from 'node:test'
import { conterFocoNoModal, fecharModalComEscape } from '../src/hooks/useModalAcessivel.js'

function elemento() {
  return { focado: false, focus() { this.focado = true }, getAttribute() { return null } }
}

test('modal mantém Tab e Shift+Tab dentro dos controles', () => {
  const primeiro = elemento()
  const ultimo = elemento()
  const modal = { querySelectorAll: () => [primeiro, ultimo], contains: (alvo) => alvo === primeiro || alvo === ultimo }
  let prevenido = false
  conterFocoNoModal({ key: 'Tab', shiftKey: false, preventDefault: () => { prevenido = true } }, modal, { activeElement: ultimo })
  assert.equal(prevenido, true)
  assert.equal(primeiro.focado, true)

  prevenido = false
  conterFocoNoModal({ key: 'Tab', shiftKey: true, preventDefault: () => { prevenido = true } }, modal, { activeElement: primeiro })
  assert.equal(prevenido, true)
  assert.equal(ultimo.focado, true)
})

test('modal sem controles mantém foco no próprio diálogo', () => {
  const modal = { focado: false, querySelectorAll: () => [], focus() { this.focado = true } }
  let prevenido = false
  conterFocoNoModal({ key: 'Tab', preventDefault: () => { prevenido = true } }, modal)
  assert.equal(prevenido, true)
  assert.equal(modal.focado, true)
})

test('Escape fecha somente quando a operação permite', () => {
  let fechamentos = 0
  fecharModalComEscape({ key: 'Escape' }, true, () => { fechamentos += 1 })
  fecharModalComEscape({ key: 'Enter' }, false, () => { fechamentos += 1 })
  assert.equal(fechamentos, 0)
  fecharModalComEscape({ key: 'Escape' }, false, () => { fechamentos += 1 })
  assert.equal(fechamentos, 1)
})
