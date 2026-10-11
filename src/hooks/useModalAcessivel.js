import { useEffect, useRef } from 'react'

const SELETOR_FOCAVEL = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])',
  'select:not([disabled])', 'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function conterFocoNoModal(evento, modal, documento = globalThis.document) {
  if (evento.key !== 'Tab' || !modal) return
  const focaveis = [...modal.querySelectorAll(SELETOR_FOCAVEL)].filter((item) => (
    item.getAttribute?.('aria-hidden') !== 'true'
  ))
  if (!focaveis.length) {
    evento.preventDefault()
    modal.focus?.()
    return
  }
  const primeiro = focaveis[0]
  const ultimo = focaveis.at(-1)
  const ativo = documento?.activeElement
  if (evento.shiftKey && (ativo === primeiro || !modal.contains?.(ativo))) {
    evento.preventDefault()
    ultimo.focus()
  } else if (!evento.shiftKey && (ativo === ultimo || !modal.contains?.(ativo))) {
    evento.preventDefault()
    primeiro.focus()
  }
}

export function fecharModalComEscape(evento, bloqueado, aoFechar) {
  if (evento.key === 'Escape' && !bloqueado) aoFechar?.()
}

export default function useModalAcessivel({ aberto = true, bloqueado = false, aoFechar, focoInicialRef, retornoFocoRef }) {
  const modalRef = useRef(null)
  const retornoInternoRef = useRef(null)

  useEffect(() => {
    if (!aberto) return undefined
    retornoInternoRef.current = retornoFocoRef?.current ?? globalThis.document?.activeElement ?? null
    const alvo = focoInicialRef?.current ?? modalRef.current
    alvo?.focus?.()
    return () => {
      const retorno = retornoInternoRef.current
      retornoInternoRef.current = null
      if (!retorno?.focus || retorno.isConnected === false) return
      if (typeof globalThis.requestAnimationFrame === 'function') globalThis.requestAnimationFrame(() => { if (retorno.isConnected !== false) retorno.focus() })
      else retorno.focus()
    }
  }, [aberto, focoInicialRef, retornoFocoRef])

  useEffect(() => {
    if (!aberto) return undefined
    const fechar = (evento) => fecharModalComEscape(evento, bloqueado, aoFechar)
    globalThis.window?.addEventListener?.('keydown', fechar)
    return () => globalThis.window?.removeEventListener?.('keydown', fechar)
  }, [aberto, bloqueado, aoFechar])

  function aoPressionarTecla(evento) {
    conterFocoNoModal(evento, modalRef.current)
  }

  return { modalRef, aoPressionarTecla }
}
