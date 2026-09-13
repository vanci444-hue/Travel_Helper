import { useCallback, useEffect, useState, type KeyboardEvent, type PointerEvent } from 'react'

export const RIGHT_COL_MIN = 280
export const RIGHT_COL_MAX = 720
export const RIGHT_COL_DEFAULT = 400
const STORAGE_KEY = 'xtrip.rightColWidth'

function clampWidth(value: number) {
  return Math.min(RIGHT_COL_MAX, Math.max(RIGHT_COL_MIN, Math.round(value)))
}

export function useRightColWidth() {
  const [width, setWidth] = useState(RIGHT_COL_DEFAULT)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    try {
      const stored = Number(window.localStorage.getItem(STORAGE_KEY))
      if (Number.isFinite(stored) && stored > 0) setWidth(clampWidth(stored))
    } catch {
      /* ignore */
    }
  }, [])

  const commit = useCallback((next: number) => {
    const value = clampWidth(next)
    setWidth(value)
    try {
      window.localStorage.setItem(STORAGE_KEY, String(value))
    } catch {
      /* ignore */
    }
  }, [])

  const onPointerDown = useCallback(
    (event: PointerEvent<HTMLButtonElement>) => {
      if (event.button !== 0) return
      event.preventDefault()
      const startX = event.clientX
      const startWidth = width
      const handle = event.currentTarget
      handle.setPointerCapture(event.pointerId)
      setDragging(true)

      function onMove(moveEvent: globalThis.PointerEvent) {
        commit(startWidth + (startX - moveEvent.clientX))
      }
      function onUp(upEvent: globalThis.PointerEvent) {
        handle.releasePointerCapture(upEvent.pointerId)
        setDragging(false)
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
        window.removeEventListener('pointercancel', onUp)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
      window.addEventListener('pointercancel', onUp)
    },
    [commit, width],
  )

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        commit(width + 16)
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        commit(width - 16)
      } else if (event.key === 'Home') {
        event.preventDefault()
        commit(RIGHT_COL_MAX)
      } else if (event.key === 'End') {
        event.preventDefault()
        commit(RIGHT_COL_MIN)
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        commit(RIGHT_COL_DEFAULT)
      }
    },
    [commit, width],
  )

  const onDoubleClick = useCallback(() => {
    commit(RIGHT_COL_DEFAULT)
  }, [commit])

  return { width, dragging, onPointerDown, onKeyDown, onDoubleClick }
}
