import { useCallback, useEffect, useState } from 'react'
import type { ConversationPublic, PlanningPublic } from '../types/conversation'
import {
  deleteItineraryCard,
  getItinerary,
  getItineraryConversation,
  listItineraries,
  reviseItinerary,
  type ItineraryListItem,
  type ItineraryPublic,
  type ListItinerariesQuery,
} from '../services/itineraryService'

export function useTripList(query: ListItinerariesQuery = {}) {
  const [items, setItems] = useState<ItineraryListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const empty = Boolean(query.empty)
  const page = query.page ?? 1
  const pageSize = query.page_size ?? 20

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listItineraries({ empty, page, page_size: pageSize })
      .then((result) => {
        if (!cancelled) setItems(result.items)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : '行程列表加载失败')
          setItems([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [empty, page, pageSize])

  return { items, loading, error }
}

export function useItinerary(itineraryId: string | undefined) {
  const [itinerary, setItinerary] = useState<ItineraryPublic | null>(null)
  const [conversation, setConversation] = useState<ConversationPublic | null>(null)
  const [planning, setPlanning] = useState<PlanningPublic | null>(null)
  const [loading, setLoading] = useState(true)
  const [revising, setRevising] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!itineraryId) {
      setItinerary(null)
      setConversation(null)
      setPlanning(null)
      setLoading(false)
      setError('缺少行程')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const next = await getItinerary(itineraryId)
      setItinerary(next)
      try {
        const thread = await getItineraryConversation(next.conversation_id)
        setConversation(thread)
        setPlanning(thread.planning)
      } catch {
        setConversation(null)
        setPlanning(null)
      }
    } catch (caught) {
      setItinerary(null)
      setConversation(null)
      setPlanning(null)
      setError(caught instanceof Error ? caught.message : '行程不存在')
    } finally {
      setLoading(false)
    }
  }, [itineraryId])

  useEffect(() => {
    void reload()
  }, [reload])

  const deleteCard = useCallback(
    async (cardId: string) => {
      if (!itineraryId) return
      const next = await deleteItineraryCard(itineraryId, cardId)
      setItinerary(next)
      try {
        const thread = await getItineraryConversation(next.conversation_id)
        setConversation(thread)
        setPlanning(thread.planning)
      } catch {
        /* 删卡已成功，规划状态仅用于核对专员未重跑 */
      }
    },
    [itineraryId],
  )

  const sendRevision = useCallback(
    async (content: string) => {
      if (!itineraryId || !itinerary) {
        throw new Error('缺少行程')
      }
      setRevising(true)
      try {
        const result = await reviseItinerary(itineraryId, itinerary.conversation_id, content)
        setItinerary(result.itinerary)
        setPlanning(result.turn.planning)
        setConversation((current) => {
          if (!current) {
            return {
              id: result.itinerary.conversation_id,
              title: result.itinerary.title,
              intake: result.turn.intake,
              map_hint: null,
              planning: result.turn.planning,
              messages: [result.turn.user_message, result.turn.assistant_message],
              created_at: result.itinerary.created_at,
              updated_at: result.itinerary.updated_at,
            }
          }
          return {
            ...current,
            planning: result.turn.planning,
            messages: [...current.messages, result.turn.user_message, result.turn.assistant_message],
            updated_at: result.turn.assistant_message.created_at,
          }
        })
        return result
      } finally {
        setRevising(false)
      }
    },
    [itinerary, itineraryId],
  )

  return { itinerary, conversation, planning, loading, revising, error, deleteCard, sendRevision, reload }
}
