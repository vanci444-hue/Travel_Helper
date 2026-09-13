import type { CardType, TransitMode } from '../services/itineraryService'
import type { Pace, SpecialistRole } from '../types/conversation'

export const CARD_TYPE_MARK: Record<CardType, string> = {
  attraction: '📍',
  lodging: '🏨',
  meal: '🍜',
  other: '📌',
}

export const TRANSIT_MARK: Record<TransitMode, string> = {
  transit: '🚌',
  walking: '🚶',
  mixed: '🔀',
}

export const PACE_MARK: Record<Pace, string> = {
  relaxed: '🍃',
  moderate: '🚶',
  packed: '⚡',
}

export const SPECIALIST_MARK: Record<SpecialistRole, string> = {
  destination_research: '📍',
  budget_expert: '💰',
  itinerary_design: '🗓️',
}

export function suggestMark(text: string): string {
  if (/走路|公交|交通/.test(text)) return '🚌'
  if (/住宿|住/.test(text)) return '🏨'
  if (/目的地|成都|换个/.test(text)) return '🗺️'
  if (/满|少排/.test(text)) return '🍃'
  return '✨'
}
