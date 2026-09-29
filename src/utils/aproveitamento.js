export function calcularAproveitamento(acertos, erros) {
  const total = acertos + erros

  if (total === 0) return 0

  return (acertos / total) * 100
}

export function formatarAproveitamento(acertos, erros) {
  const percentual = calcularAproveitamento(acertos, erros)
  const valorFormatado = new Intl.NumberFormat('pt-BR', {
    maximumFractionDigits: 2,
  }).format(percentual)

  return `${valorFormatado}%`
}
