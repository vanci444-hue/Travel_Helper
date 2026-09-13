import { useEffect, useRef } from 'react'
import { isMockMode } from '../services/api'
import { getConversation } from '../services/conversationService'
import type {
  ConversationPublic,
  PlanningPublic,
  SpecialistPublic,
  SpecialistRole,
} from '../types/conversation'

export type LogKind = 'tool' | 'thought' | 'specialist'

export interface ActivityLogDetail {
  heading: string
  body: string
}

export interface ActivityLogEntry {
  id: string
  kind: LogKind
  specialist: SpecialistRole
  title: string
  clickable: boolean
  detail: ActivityLogDetail | null
  created_at: string
}

export interface PlanningFailedPayload {
  status: 'failed'
  itinerary_id: null
  failure_reason: string
  coco_message_id: string
  specialists: SpecialistPublic[]
}

export interface ItineraryReadyPayload {
  status: 'succeeded'
  itinerary_id: string
  specialists: SpecialistPublic[]
}

export interface PlanningStreamHandlers {
  onLog: (entry: ActivityLogEntry) => void
  onUpdated: (patch: {
    specialists: SpecialistPublic[]
    status?: PlanningPublic['status']
    itinerary_id?: string | null
  }) => void
  onConversation: (conversation: ConversationPublic) => void
}

function planningEventUrl(conversationId: string): string {
  const base = import.meta.env.VITE_API_BASE_URL || '/api'
  return `${base.replace(/\/+$/, '')}/conversations/${conversationId}/events`
}

function parseData<T>(event: Event): T | null {
  const message = event as MessageEvent<string>
  if (typeof message.data !== 'string') return null
  try {
    return JSON.parse(message.data) as T
  } catch {
    return null
  }
}

function asActivityLog(value: unknown[] | undefined): ActivityLogEntry[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is ActivityLogEntry => {
    if (!item || typeof item !== 'object') return false
    const entry = item as ActivityLogEntry
    return typeof entry.id === 'string' && typeof entry.title === 'string'
  })
}

function isTerminal(status: PlanningPublic['status'] | undefined): boolean {
  return status === 'succeeded' || status === 'failed'
}

export function usePlanningEvents(
  conversationId: string | null,
  active: boolean,
  handlers: PlanningStreamHandlers,
): void {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  useEffect(() => {
    if (!conversationId || !active) return

    let cancelled = false
    let pollTimer: number | null = null
    let source: EventSource | null = null

    const emitSnapshot = (conversation: ConversationPublic) => {
      for (const entry of asActivityLog(conversation.planning.activity_log)) {
        handlersRef.current.onLog(entry)
      }
      handlersRef.current.onUpdated({
        specialists: conversation.planning.specialists,
        status: conversation.planning.status,
        itinerary_id: conversation.planning.itinerary_id,
      })
      handlersRef.current.onConversation(conversation)
    }

    const finishWithConversation = async () => {
      try {
        const conversation = await getConversation(conversationId)
        if (!cancelled) emitSnapshot(conversation)
      } catch {
        /* 终态以对话详情为准；拉失败则等下一轮轮询 */
      }
    }

    const pollOnce = async () => {
      try {
        const conversation = await getConversation(conversationId)
        if (cancelled) return
        emitSnapshot(conversation)
        if (isTerminal(conversation.planning.status)) {
          if (pollTimer != null) window.clearInterval(pollTimer)
          pollTimer = null
          source?.close()
        }
      } catch {
        /* 保持 2s 轮询直到终态 */
      }
    }

    const startPoll = () => {
      if (pollTimer != null) return
      void pollOnce()
      pollTimer = window.setInterval(() => {
        void pollOnce()
      }, 2000)
    }

    const attach = (target: EventSource) => {
      target.addEventListener('planning.log', (event) => {
        const payload = parseData<{ entry: ActivityLogEntry }>(event)
        if (payload?.entry) handlersRef.current.onLog(payload.entry)
      })
      target.addEventListener('planning.updated', (event) => {
        const payload = parseData<{
          status?: PlanningPublic['status']
          specialists: SpecialistPublic[]
          itinerary_id?: string | null
        }>(event)
        if (payload?.specialists) handlersRef.current.onUpdated(payload)
      })
      target.addEventListener('itinerary.ready', (event) => {
        const payload = parseData<ItineraryReadyPayload>(event)
        if (payload) {
          handlersRef.current.onUpdated({
            status: 'succeeded',
            specialists: payload.specialists,
            itinerary_id: payload.itinerary_id,
          })
        }
        void finishWithConversation()
      })
      target.addEventListener('planning.failed', (event) => {
        const payload = parseData<PlanningFailedPayload>(event)
        if (payload) {
          handlersRef.current.onUpdated({
            status: 'failed',
            specialists: payload.specialists,
            itinerary_id: null,
          })
        }
        void finishWithConversation()
      })
      target.addEventListener('error', () => {
        startPoll()
      })
    }

    const connect = async () => {
      if (isMockMode) {
        const { startPlanningMockStream } = await import('../mocks/planning')
        if (cancelled) return
        source = startPlanningMockStream(conversationId) as unknown as EventSource
        attach(source)
        return
      }
      source = new EventSource(planningEventUrl(conversationId))
      attach(source)
      startPoll()
    }

    void connect()

    return () => {
      cancelled = true
      source?.close()
      if (isMockMode) {
        void import('../mocks/planning').then(({ releasePlanningStream }) => {
          releasePlanningStream(conversationId)
        })
      }
      if (pollTimer != null) window.clearInterval(pollTimer)
    }
  }, [conversationId, active])
}
