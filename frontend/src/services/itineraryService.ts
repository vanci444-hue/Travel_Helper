import { AxiosError } from 'axios'
import api, { isMockMode } from './api'
import type { ApiEnvelope } from '../types/api'
import type { Pace } from '../types/conversation'
import { getConversation, sendMessage, type MessageTurnPublic } from './conversationService'
import {
  deleteItineraryCardMock,
  getItineraryMock,
  listItinerariesMock,
} from '../mocks/itineraries'

export type CardType = 'attraction' | 'lodging' | 'meal' | 'other'
export type TransitMode = 'transit' | 'walking' | 'mixed'
export type LegSource = 'amap' | 'estimate'
export type ItineraryStatus = 'ready'

export const PACE_LABEL: Record<Pace, string> = {
  relaxed: '轻松',
  moderate: '适中',
  packed: '紧凑',
}

export const CARD_TYPE_LABEL: Record<CardType, string> = {
  attraction: '景点',
  lodging: '住宿',
  meal: '餐饮',
  other: '其他',
}

export interface ItineraryListItem {
  id: string
  title: string
  destination_city: string
  duration_days: number
  pace: Pace
  updated_at: string
  conversation_id: string
}

export interface ItineraryCardPublic {
  id: string
  type: CardType
  title: string
  poi_id: string | null
  lng: number | null
  lat: number | null
  address: string | null
  intro: string | null
  photo_url: string | null
  start_time: string | null
  suitable_for_children: boolean
}

export interface TransitLegPublic {
  mode: TransitMode
  duration_min: number | null
  distance_m: number | null
  summary: string
  source: LegSource
}

export interface ItineraryDayPublic {
  day_index: number
  label: string
  date: string | null
  cards: ItineraryCardPublic[]
  legs: TransitLegPublic[]
}

export interface BudgetCategoryPublic {
  key: string
  label: string
  amount: number
}

export interface BudgetPublic {
  currency: string
  cap_amount: number
  total_amount: number
  over_cap: boolean
  includes_note: string
  categories: BudgetCategoryPublic[]
}

export interface ChecklistItemPublic {
  id: string
  text: string
  relevant: boolean
}

export interface QuickSuggestionPublic {
  id: string
  text: string
}

export interface MapPointPublic {
  lng: number
  lat: number
}

export interface ItineraryPublic {
  id: string
  conversation_id: string
  title: string
  destination_city: string
  origin_city: string
  duration_days: number
  pace: Pace
  companion_type: string
  assumptions: string[]
  days: ItineraryDayPublic[]
  budget: BudgetPublic
  checklist: ChecklistItemPublic[]
  map_center: MapPointPublic
  quick_suggestions: QuickSuggestionPublic[]
  status: ItineraryStatus
  created_at: string
  updated_at: string
}

export interface PaginationPublic {
  page: number
  page_size: number
  total_items: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

export interface ItineraryListResult {
  items: ItineraryListItem[]
  pagination: PaginationPublic
}

export interface ListItinerariesQuery {
  page?: number
  page_size?: number
  empty?: boolean
}

function unwrap<T>(result: { status: number; body: ApiEnvelope<T | null> }, fallback: string): T {
  if (result.status >= 400 || !result.body.data) {
    throw new Error(result.body.error || fallback)
  }
  return result.body.data
}

export async function listItineraries(query: ListItinerariesQuery = {}): Promise<ItineraryListResult> {
  if (isMockMode) {
    const result = listItinerariesMock(query)
    const items = unwrap(result, '行程列表加载失败')
    return {
      items,
      pagination: result.body.pagination,
    }
  }

  try {
    const response = await api.get<ApiEnvelope<ItineraryListItem[]> & { pagination?: PaginationPublic }>(
      '/itineraries',
      { params: { page: query.page ?? 1, page_size: query.page_size ?? 20 } },
    )
    if (!response.data.data) {
      throw new Error(response.data.error || '行程列表加载失败')
    }
    const pagination = response.data.pagination ?? {
      page: query.page ?? 1,
      page_size: query.page_size ?? 20,
      total_items: response.data.data.length,
      total_pages: 1,
      has_next: false,
      has_prev: false,
    }
    return { items: response.data.data, pagination }
  } catch (error) {
    if (error instanceof AxiosError) {
      const body = error.response?.data as ApiEnvelope<null> | undefined
      throw new Error(body?.error || '行程列表加载失败')
    }
    throw error
  }
}

export async function getItinerary(itineraryId: string): Promise<ItineraryPublic> {
  if (isMockMode) {
    return unwrap(getItineraryMock(itineraryId), '行程不存在')
  }

  try {
    const response = await api.get<ApiEnvelope<ItineraryPublic>>(`/itineraries/${itineraryId}`)
    if (!response.data.data) {
      throw new Error(response.data.error || '行程不存在')
    }
    return response.data.data
  } catch (error) {
    if (error instanceof AxiosError) {
      const body = error.response?.data as ApiEnvelope<null> | undefined
      throw new Error(body?.error || '行程不存在')
    }
    throw error
  }
}

export async function getItineraryConversation(conversationId: string) {
  return getConversation(conversationId)
}

export async function reviseItinerary(
  itineraryId: string,
  conversationId: string,
  content: string,
): Promise<{ itinerary: ItineraryPublic; turn: MessageTurnPublic }> {
  const turn = await sendMessage(conversationId, content)
  const itinerary = await getItinerary(itineraryId)
  return { itinerary, turn }
}

export async function deleteItineraryCard(
  itineraryId: string,
  cardId: string,
): Promise<ItineraryPublic> {
  if (isMockMode) {
    return unwrap(deleteItineraryCardMock(itineraryId, cardId), '删除卡片失败')
  }

  try {
    const response = await api.delete<ApiEnvelope<ItineraryPublic>>(
      `/itineraries/${itineraryId}/cards/${cardId}`,
    )
    if (!response.data.data) {
      throw new Error(response.data.error || '删除卡片失败')
    }
    return response.data.data
  } catch (error) {
    if (error instanceof AxiosError) {
      const body = error.response?.data as ApiEnvelope<null> | undefined
      throw new Error(body?.error || '删除卡片失败')
    }
    throw error
  }
}

export function formatUpdatedAt(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const now = new Date()
  if (date.toDateString() === now.toDateString()) return '今天'
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

export function formatMoneyWan(amount: number): string {
  if (amount >= 10000) {
    const wan = amount / 10000
    const text = Number.isInteger(wan) ? String(wan) : wan.toFixed(1).replace(/\.0$/, '')
    return `${text} 万`
  }
  return String(amount)
}

export function isDestinationChange(text: string): boolean {
  return /换目的地|改去|换个城市|换个地方/.test(text)
}
