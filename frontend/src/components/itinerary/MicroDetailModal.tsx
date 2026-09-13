import { useEffect } from 'react'
import type { ItineraryCardPublic } from '../../services/itineraryService'
import { CARD_TYPE_MARK } from '../../ui/travelMarks'

export function MicroDetailModal({
  card,
  onClose,
}: {
  card: ItineraryCardPublic | null
  onClose: () => void
}) {
  useEffect(() => {
    if (!card) return
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [card, onClose])

  if (!card) return null

  const body = [card.intro, card.address].filter(Boolean).join(' ')

  return (
    <div className="overlay" onClick={onClose} role="presentation">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="micro-detail-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="micro-detail-title">
          <span className="ui-mark" aria-hidden="true">
            {CARD_TYPE_MARK[card.type]}
          </span>
          {card.title}
        </h2>
        <p className="micro-detail-body">{body || '暂无简介'}</p>
        <div className="modal-actions">
          <button type="button" className="cta-btn" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
