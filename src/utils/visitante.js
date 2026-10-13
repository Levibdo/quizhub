export const CHAVE_VISITANTE_ID = 'quizhub-visitante-id'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function visitanteIdValido(valor) {
  return typeof valor === 'string' && UUID_V4.test(valor)
}

function gerarUuidV4(cryptoApi) {
  if (typeof cryptoApi?.randomUUID === 'function') return cryptoApi.randomUUID()
  if (typeof cryptoApi?.getRandomValues !== 'function') {
    throw new Error('Este navegador não oferece geração segura de identificadores.')
  }
  const bytes = cryptoApi.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hexadecimal = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hexadecimal.slice(0, 8)}-${hexadecimal.slice(8, 12)}-${hexadecimal.slice(12, 16)}-${hexadecimal.slice(16, 20)}-${hexadecimal.slice(20)}`
}

export function obterVisitanteId(
  storage = globalThis.localStorage,
  cryptoApi = globalThis.crypto,
) {
  const existente = storage?.getItem?.(CHAVE_VISITANTE_ID)
  if (visitanteIdValido(existente)) return existente.toLowerCase()

  const novo = gerarUuidV4(cryptoApi)
  if (!visitanteIdValido(novo)) throw new Error('Não foi possível gerar a identidade do visitante.')
  storage?.setItem?.(CHAVE_VISITANTE_ID, novo)
  return novo
}
