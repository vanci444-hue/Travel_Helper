import { useCallback, useEffect, useMemo, useState } from 'react'
import { isMockMode } from '../services/api'
import { createConversation, getConversation, sendMessage } from '../services/conversationService'
import { asActivityLog, seedPlanningConversation, type ActivityLogEntry } from '../mocks/planning'
import { useApp } from '../stores/AppProvider'
import type {
  ConversationPublic,
  IntakePublic,
  MessagePublic,
  PlanningPublic,
} from '../types/conversation'
import { usePlanningEvents } from './usePlanningEvents'

const CONVERSATION_STORAGE_KEY = 'xtrip_conversation_id'

function readStoredConversationId(): string | null {
  try {
    return window.localStorage.getItem(CONVERSATION_STORAGE_KEY)?.trim() || null
  } catch {
    return null
  }
}

function writeStoredConversationId(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(CONVERSATION_STORAGE_KEY, id)
    else window.localStorage.removeItem(CONVERSATION_STORAGE_KEY)
  } catch {
    /* 本机 Demo 存不了 id 不影响当次对话 */
  }
}

const EMPTY_PLANNING: PlanningPublic = {
  status: 'idle',
  specialists: [
    { role: 'destination_research', status: 'not_started', summary: null },
    { role: 'budget_expert', status: 'not_started', summary: null },
    { role: 'itinerary_design', status: 'not_started', summary: null },
  ],
  activity_log: [],
  error_message: null,
  itinerary_id: null,
}

export interface ConversationViewState {
  conversationId: string | null
  messages: MessagePublic[]
  planning: PlanningPublic
  intake: IntakePublic | null
  activityLog: ActivityLogEntry[]
  logHostId: string | null
  waitingCoco: boolean
  sending: boolean
  hasStarted: boolean
  sendError: string | null
  send: (text: string) => Promise<void>
}

function visibleMessages(messages: MessagePublic[]): MessagePublic[] {
  return messages.filter((item) => item.role !== 'system')
}

function startedFrom(messages: MessagePublic[]): boolean {
  return visibleMessages(messages).length > 0
}

function pickLogHost(conversation: ConversationPublic): string | null {
  const assistants = conversation.messages.filter((item) => item.role === 'assistant')
  if (conversation.planning.status !== 'idle') {
    return assistants.at(-1)?.id ?? null
  }
  const host = assistants.find(
    (item) => item.content.includes('出一版') || item.content.includes('过程会写在下面的日志里'),
  )
  return host?.id ?? null
}

export function useConversation(): ConversationViewState {
  const { conversation: seeded } = useApp()
  const [conversationId, setConversationId] = useState<string | null>(seeded?.id ?? null)
  const [messages, setMessages] = useState<MessagePublic[]>(() => visibleMessages(seeded?.messages ?? []))
  const [planning, setPlanning] = useState<PlanningPublic>(seeded?.planning ?? EMPTY_PLANNING)
  const [intake, setIntake] = useState<IntakePublic | null>(seeded?.intake ?? null)
  const [logHostId, setLogHostId] = useState<string | null>(null)
  const [waitingCoco, setWaitingCoco] = useState(false)
  const [sending, setSending] = useState(false)
  const [hasStarted, setHasStarted] = useState(() => startedFrom(seeded?.messages ?? []))
  const [sendError, setSendError] = useState<string | null>(null)

  const applyConversation = useCallback((conversation: ConversationPublic) => {
    writeStoredConversationId(conversation.id)
    setConversationId(conversation.id)
    const nextMessages = visibleMessages(conversation.messages)
    setMessages(nextMessages)
    setPlanning(conversation.planning)
    setIntake(conversation.intake)
    if (startedFrom(conversation.messages)) setHasStarted(true)
    setLogHostId((current) => current ?? pickLogHost(conversation))
  }, [])

  useEffect(() => {
    if (!seeded) return
    if (isMockMode) seedPlanningConversation(seeded)
    writeStoredConversationId(seeded.id)
    if (conversationId === seeded.id) {
      if (startedFrom(seeded.messages)) {
        setMessages(visibleMessages(seeded.messages))
        setPlanning(seeded.planning)
        setIntake(seeded.intake)
        setHasStarted(true)
        setLogHostId((current) => current ?? pickLogHost(seeded))
      }
      return
    }
    setConversationId(seeded.id)
    setMessages(visibleMessages(seeded.messages))
    setPlanning(seeded.planning)
    setIntake(seeded.intake)
    setLogHostId(pickLogHost(seeded))
    setHasStarted(startedFrom(seeded.messages))
  }, [conversationId, seeded])

  useEffect(() => {
    if (seeded || isMockMode || conversationId) return
    const storedId = readStoredConversationId()
    if (!storedId) return
    let cancelled = false
    void getConversation(storedId)
      .then((conversation) => {
        if (cancelled) return
        applyConversation(conversation)
      })
      .catch(() => {
        if (cancelled) return
        writeStoredConversationId(null)
      })
    return () => {
      cancelled = true
    }
  }, [applyConversation, conversationId, seeded])

  usePlanningEvents(conversationId, planning.status === 'running', {
    onLog: (entry) => {
      setPlanning((current) => {
        const logs = asActivityLog(current.activity_log)
        if (logs.some((item) => item.id === entry.id)) return current
        return { ...current, activity_log: [...logs, entry] }
      })
    },
    onUpdated: (patch) => {
      setPlanning((current) => ({
        ...current,
        status:
          patch.status === 'succeeded' || patch.status === 'failed'
            ? current.status
            : (patch.status ?? current.status),
        specialists: patch.specialists,
        itinerary_id: patch.itinerary_id === undefined ? current.itinerary_id : patch.itinerary_id,
      }))
    },
    onConversation: applyConversation,
  })

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return

    const optimistic: MessagePublic = {
      id: `local_${Date.now()}`,
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
    }
    setMessages((current) => [...current, optimistic])
    setHasStarted(true)
    setWaitingCoco(true)
    setSending(true)
    setSendError(null)

    try {
      let id = conversationId
      if (!id) {
        const created = await createConversation({})
        id = created.id
        writeStoredConversationId(id)
        setConversationId(id)
        setIntake(created.intake)
        setPlanning(created.planning)
      }

      const turn = await sendMessage(id, trimmed)
      setIntake(turn.intake)
      setPlanning({
        ...turn.planning,
        activity_log: turn.planning.status === 'running' ? [] : turn.planning.activity_log,
      })
      if (turn.planning.status === 'running') {
        setLogHostId(turn.assistant_message.id)
      }
      setMessages((current) => {
        const withoutOptimistic = current.filter((item) => item.id !== optimistic.id)
        return [...withoutOptimistic, turn.user_message, turn.assistant_message]
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Coco 暂时没有回复，请再试一次'
      setSendError(message)
      setMessages((current) => [
        ...current,
        {
          id: `err_${Date.now()}`,
          role: 'assistant',
          display_name: 'Coco',
          content: message,
          created_at: new Date().toISOString(),
        },
      ])
    } finally {
      setWaitingCoco(false)
      setSending(false)
    }
  }, [conversationId])

  const activityLog = useMemo(() => asActivityLog(planning.activity_log), [planning.activity_log])

  return {
    conversationId,
    messages,
    planning,
    intake,
    activityLog,
    logHostId,
    waitingCoco,
    sending,
    hasStarted,
    sendError,
    send,
  }
}
