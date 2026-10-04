import { requisitar } from './api.js'

const CHAVE_SESSOES = 'quizhub-nem-pato-sessoes'

function lerSessoes() {
  try {
    const dados = JSON.parse(localStorage.getItem(CHAVE_SESSOES) || '{}')
    return dados && typeof dados === 'object' && !Array.isArray(dados) ? dados : {}
  } catch {
    return {}
  }
}

export function carregarSessaoNemAPato(codigo) {
  const chave = codigo?.trim().toUpperCase()
  if (!chave) return null
  const sessao = lerSessoes()[chave]
  return sessao?.codigo === chave && typeof sessao.token === 'string' && sessao.token
    ? sessao
    : null
}

export function salvarSessaoNemAPato(codigo, token) {
  const chave = codigo.trim().toUpperCase()
  const sessoes = lerSessoes()
  sessoes[chave] = { codigo: chave, token }
  localStorage.setItem(CHAVE_SESSOES, JSON.stringify(sessoes))
}

export function removerSessaoNemAPato(codigo) {
  const chave = codigo?.trim().toUpperCase()
  if (!chave) return
  const sessoes = lerSessoes()
  delete sessoes[chave]
  localStorage.setItem(CHAVE_SESSOES, JSON.stringify(sessoes))
}

export function criarSalaNemAPato(nome) {
  return requisitar('/api/v1/nem-pato/salas', {
    method: 'POST',
    body: JSON.stringify({ nome }),
  })
}

export function entrarSalaNemAPato(codigo, nome) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}/participantes`, {
    method: 'POST',
    body: JSON.stringify({ nome }),
  })
}

export function obterSalaNemAPato(codigo) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}`, {
    method: 'GET',
  })
}

export function recuperarSalaNemAPato(codigo, token) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}/eu`, {
    method: 'GET',
    headers: { 'X-Nem-Pato-Token': token },
  })
}

export function iniciarPartidaNemAPato(codigo, token) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}/iniciar`, {
    method: 'POST',
    headers: { 'X-Nem-Pato-Token': token },
  })
}

export function jogarNovamenteNemAPato(codigo, token) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}/jogar-novamente`, {
    method: 'POST',
    headers: { 'X-Nem-Pato-Token': token },
  })
}

export function iniciarRodadaNemAPato(codigo, token) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}/rodadas/iniciar`, {
    method: 'POST',
    headers: { 'X-Nem-Pato-Token': token },
  })
}

export function enviarPalpiteNemAPato(codigo, rodadaId, token, valor, clientActionId) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}/rodadas/${encodeURIComponent(rodadaId)}/palpites`, {
    method: 'POST',
    headers: { 'X-Nem-Pato-Token': token },
    body: JSON.stringify({ valor, client_action_id: clientActionId }),
  })
}

export function desafiarPalpiteNemAPato(codigo, rodadaId, token, clientActionId) {
  return requisitar("/api/v1/nem-pato/salas/" + encodeURIComponent(codigo) + "/rodadas/" + encodeURIComponent(rodadaId) + "/desafiar", {
    method: "POST",
    headers: { "X-Nem-Pato-Token": token },
    body: JSON.stringify({ client_action_id: clientActionId }),
  })
}

export function iniciarProximaRodadaNemAPato(codigo, rodadaId, token) {
  return requisitar("/api/v1/nem-pato/salas/" + encodeURIComponent(codigo) + "/rodadas/" + encodeURIComponent(rodadaId) + "/proxima", {
    method: "POST",
    headers: { "X-Nem-Pato-Token": token },
  })
}

export function abandonarSalaNemAPato(codigo, token) {
  return requisitar(`/api/v1/nem-pato/salas/${encodeURIComponent(codigo)}/abandonar`, {
    method: 'POST',
    headers: { 'X-Nem-Pato-Token': token },
  })
}

export { CHAVE_SESSOES }
