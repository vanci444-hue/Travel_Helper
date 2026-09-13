import { useEffect, useRef, useState } from 'react'
import { CARD_TYPE_LABEL, type ItineraryCardPublic } from '../../services/itineraryService'
import { CARD_TYPE_MARK } from '../../ui/travelMarks'
import { BORDER_GLOW_COLORS, BorderGlow } from '../ui/BorderGlow'

export function ItineraryCard({
  card,
  onOpen,
  onDelete,
}: {
  card: ItineraryCardPublic
  onOpen: (card: ItineraryCardPublic) => void
  onDelete?: (cardId: string) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    function handlePointer(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handlePointer)
    return () => document.removeEventListener('mousedown', handlePointer)
  }, [menuOpen])

  return (
    <BorderGlow
      className="itinerary-glow"
      backgroundColor="#2f2f2f"
      borderRadius={14}
      glowRadius={20}
      glowIntensity={0.9}
      glowColor="40 80 80"
      colors={[...BORDER_GLOW_COLORS]}
    >
    <article className="itinerary-card">
      <button type="button" className="itinerary-card-main" onClick={() => onOpen(card)}>
        <strong>
          <span className="ui-mark" aria-hidden="true">
            {CARD_TYPE_MARK[card.type]}
          </span>
          {card.title}
        </strong>
        <span className="itinerary-card-meta">
          {CARD_TYPE_LABEL[card.type]}
          {card.start_time ? ` · ${card.start_time}` : ''}
          {card.address ? ` · ${card.address}` : ''}
        </span>
      </button>
      {onDelete ? (
        <div className="itinerary-card-more" ref={menuRef}>
          <button
            type="button"
            className="icon-btn"
            aria-label="更多操作"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            …
          </button>
          {menuOpen ? (
            <div className="itinerary-card-menu">
              <button
                type="button"
                className="text-btn"
                onClick={() => {
                  setMenuOpen(false)
                  onDelete(card.id)
                }}
              >
                删除
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
    </BorderGlow>
  )
}
