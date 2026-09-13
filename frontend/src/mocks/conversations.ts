import { makeEnvelope, makeErrorEnvelope, type MockHttpResult } from '../types/api'
import {
  PACE_VALUES,
  type CompanionType,
  type ConversationCreate,
  type ConversationPublic,
  type IntakePublic,
  type Pace,
  type Region,
} from '../types/conversation'

let conversationSeq = 1

const EMPTY_SPECIALISTS = [
  { role: 'destination_research' as const, status: 'not_started' as const, summary: null },
  { role: 'budget_expert' as const, status: 'not_started' as const, summary: null },
  { role: 'itinerary_design' as const, status: 'not_started' as const, summary: null },
]

function inferCompanionType(adults: number | null, children: number | null): CompanionType | null {
  if (adults == null && children == null) return null
  const adultCount = adults ?? 0
  const childCount = children ?? 0
  if (childCount > 0) return 'parent_child'
  if (adultCount === 1) return 'solo'
  if (adultCount === 2) return 'couple'
  if (adultCount > 2) return 'friends'
  return 'unknown'
}

function inferRegion(destinationCity: string | null, destinationText: string | null): Region | null {
  if (destinationCity || destinationText) return 'domestic'
  return null
}

function missingFieldsOf(intake: Omit<IntakePublic, 'missing_fields' | 'followup_rounds_used' | 'ready'>): string[] {
  const missing: string[] = []
  if (!intake.origin_city) missing.push('origin_city')
  if (!intake.region) missing.push('region')
  if (!intake.destination_city && !intake.destination_text) missing.push('destination_city')
  if (intake.duration_days == null && !intake.date_month && !intake.date_start) {
    missing.push('duration_days')
  }
  if (intake.adults == null && intake.children == null) missing.push('companion_type')
  if (intake.budget_amount_cny == null && !intake.budget_tier) missing.push('budget_amount_cny')
  if (!intake.pace) missing.push('pace')
  return missing
}

function titleOf(input: ConversationCreate): string {
  const city = input.destination_city || input.destination_text
  if (city && input.duration_days) return `${city} ${input.duration_days} 天`
  if (city) return city
  return '新对话'
}

function toConversationPublic(input: ConversationCreate): ConversationPublic {
  const destinationText = input.destination_text ?? null
  const destinationCity = input.destination_city ?? destinationText
  const adults = input.adults ?? null
  const children = input.children ?? null
  const baseIntake = {
    origin_city: input.origin_city ?? null,
    region: input.region ?? inferRegion(destinationCity, destinationText),
    destination_text: destinationText,
    destination_city: destinationCity,
    duration_days: input.duration_days ?? null,
    date_start: input.date_start ?? null,
    date_end: input.date_end ?? null,
    date_month: input.date_month ?? null,
    companion_type: input.companion_type ?? inferCompanionType(adults, children),
    adults,
    children,
    children_age_bands: input.children_age_bands ?? [],
    budget_amount_cny: input.budget_amount_cny ?? null,
    budget_tier: input.budget_tier ?? null,
    budget_includes: input.budget_includes ?? 'domestic_transport_and_local',
    pace: input.pace ?? null,
    wish_text: input.wish_text ?? null,
  }
  const missing_fields = missingFieldsOf(baseIntake)
  const now = new Date().toISOString()
  const id = `conv_mock_${String(conversationSeq).padStart(2, '0')}`
  conversationSeq += 1

  return {
    id,
    title: titleOf(input),
    intake: {
      ...baseIntake,
      missing_fields,
      followup_rounds_used: 0,
      ready: missing_fields.length === 0,
    },
    map_hint: null,
    planning: {
      status: 'idle',
      specialists: EMPTY_SPECIALISTS.map((item) => ({ ...item })),
      activity_log: [],
      error_message: null,
      itinerary_id: null,
    },
    messages: [],
    created_at: now,
    updated_at: now,
  }
}

export function createConversationMock(input: ConversationCreate): MockHttpResult<ConversationPublic | null> {
  if (input.pace != null && !PACE_VALUES.includes(input.pace as Pace)) {
    return {
      status: 400,
      body: makeErrorEnvelope('节奏只能是轻松、适中或紧凑', 'VALIDATION_ERROR'),
    }
  }

  const data = toConversationPublic(input)
  return {
    status: 201,
    body: makeEnvelope({
      id: data.id,
      title: data.title,
      intake: { ...data.intake },
      map_hint: data.map_hint,
      planning: {
        status: data.planning.status,
        specialists: data.planning.specialists.map((item) => ({ ...item })),
        activity_log: [],
        error_message: data.planning.error_message,
        itinerary_id: data.planning.itinerary_id,
      },
      messages: [],
      created_at: data.created_at,
      updated_at: data.updated_at,
    }),
  }
}
