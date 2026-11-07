export const CHAVE_PARTIDA_CLASSICA_ATIVA = 'quizhub-classic-active-partida'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function partidaIdValido(valor) {
  return typeof valor === 'string' && UUID.test(valor)
}

export function obterPartidaClassicaAtiva(storage = globalThis.localStorage) {
  const valor = storage?.getItem?.(CHAVE_PARTIDA_CLASSICA_ATIVA)
  return partidaIdValido(valor) ? valor.toLowerCase() : null
}

export function salvarPartidaClassicaAtiva(partidaId, storage = globalThis.localStorage) {
  if (!partidaIdValido(partidaId)) throw new TypeError('Identificador de partida inválido')
  storage?.setItem?.(CHAVE_PARTIDA_CLASSICA_ATIVA, partidaId.toLowerCase())
}

export function limparPartidaClassicaAtiva(storage = globalThis.localStorage) {
  storage?.removeItem?.(CHAVE_PARTIDA_CLASSICA_ATIVA)
}

export function partidaIdDaRota(caminho = globalThis.window?.location?.pathname) {
  const correspondencia = /^\/quiz\/([^/]+)\/?$/.exec(caminho ?? '')
  return partidaIdValido(correspondencia?.[1]) ? correspondencia[1].toLowerCase() : null
}
