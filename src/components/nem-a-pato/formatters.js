export function formatarTempo(segundos) {
  const minutos = Math.floor(segundos / 60)
  return `${minutos}:${String(segundos % 60).padStart(2, '0')}`
}

export function formatarPalpite(valor, unidade) {
  if (valor === null || valor === undefined) return '—'
  const numero = new Intl.NumberFormat('pt-BR').format(valor)
  return unidade ? `${numero} ${unidade}` : numero
}
