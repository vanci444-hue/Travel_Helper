import type { ItineraryDayPublic } from '../../services/itineraryService'

export function DayChips({
  days,
  activeDay,
  onSelect,
}: {
  days: ItineraryDayPublic[]
  activeDay: number
  onSelect: (dayIndex: number) => void
}) {
  return (
    <div className="day-chips" role="tablist" aria-label="按天切换">
      {days.map((day) => (
        <button
          key={day.day_index}
          type="button"
          role="tab"
          aria-selected={activeDay === day.day_index}
          className={`day-chip${activeDay === day.day_index ? ' is-selected' : ''}`}
          onClick={() => onSelect(day.day_index)}
        >
          {day.label}
        </button>
      ))}
    </div>
  )
}
