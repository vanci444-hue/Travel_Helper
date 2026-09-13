export type Pace = 'relaxed' | 'moderate' | 'packed'
export type Region = 'domestic' | 'outbound'
export type CompanionType =
  | 'solo'
  | 'couple'
  | 'family'
  | 'friends'
  | 'parent_child'
  | 'unknown'
export type BudgetTier = 'economy' | 'comfort' | 'premium'
export type PlanningStatus = 'idle' | 'running' | 'succeeded' | 'failed'
export type SpecialistStatus = 'not_started' | 'running' | 'succeeded' | 'failed'
export type SpecialistRole = 'destination_research' | 'budget_expert' | 'itinerary_design'
export type MessageRole = 'user' | 'assistant' | 'system'

export const PACE_VALUES: readonly Pace[] = ['relaxed', 'moderate', 'packed']

export interface ConversationCreate {
  origin_city?: string | null
  region?: Region | null
  destination_text?: string | null
  destination_city?: string | null
  duration_days?: number | null
  date_start?: string | null
  date_end?: string | null
  date_month?: string | null
  companion_type?: CompanionType | null
  adults?: number | null
  children?: number | null
  children_age_bands?: string[]
  budget_amount_cny?: number | null
  budget_tier?: BudgetTier | null
  budget_includes?: string | null
  pace?: Pace | null
  wish_text?: string | null
}

export interface IntakePublic {
  origin_city: string | null
  region: Region | null
  destination_text: string | null
  destination_city: string | null
  duration_days: number | null
  date_start: string | null
  date_end: string | null
  date_month: string | null
  companion_type: CompanionType | null
  adults: number | null
  children: number | null
  children_age_bands: string[]
  budget_amount_cny: number | null
  budget_tier: BudgetTier | null
  budget_includes: string | null
  pace: Pace | null
  wish_text: string | null
  missing_fields: string[]
  followup_rounds_used: number
  ready: boolean
}

export interface SpecialistPublic {
  role: SpecialistRole
  status: SpecialistStatus
  summary: string | null
}

export interface PlanningPublic {
  status: PlanningStatus
  specialists: SpecialistPublic[]
  activity_log: unknown[]
  error_message: string | null
  itinerary_id: string | null
}

export interface MessagePublic {
  id: string
  role: MessageRole
  display_name?: string
  content: string
  created_at: string
}

export interface ConversationPublic {
  id: string
  title: string
  intake: IntakePublic
  map_hint: unknown
  planning: PlanningPublic
  messages: MessagePublic[]
  created_at: string
  updated_at: string
}

export interface NewPlanDraft {
  destination_text: string
  when_text: string
  adults_text: string
  children_text: string
  budget_text: string
  pace: Pace | null
  wish_text: string
}
