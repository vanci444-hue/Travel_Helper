import type { QuickSuggestionPublic } from '../../services/itineraryService'
import { suggestMark } from '../../ui/travelMarks'

export function QuickSuggestions({
  items,
  onSelect,
}: {
  items: QuickSuggestionPublic[]
  onSelect: (text: string) => void
}) {
  const visible = items.slice(0, 4)
  if (visible.length === 0) return null

  return (
    <div className="quick-suggestions" aria-label="快捷建议">
      {visible.map((item) => (
        <button
          key={item.id}
          type="button"
          className="suggest-chip"
          title={item.text}
          onClick={() => onSelect(item.text)}
        >
          <span className="ui-mark" aria-hidden="true">
            {suggestMark(item.text)}
          </span>
          {item.text}
        </button>
      ))}
    </div>
  )
}
