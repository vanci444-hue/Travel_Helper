import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useNavigate } from 'react-router'
import { createConversation } from '../services/conversationService'
import { CURRENT_INSPIRATIONS } from '../data/inspirations'
import { listInspirations } from '../services/inspirationService'
import { isMockMode } from '../services/api'
import type { ConversationCreate, ConversationPublic, NewPlanDraft } from '../types/conversation'
import type { InspirationPublic } from '../types/inspiration'

export type NavKey = 'chat' | 'trips'

export interface AppContextValue {
  nav: NavKey
  setNav: (nav: NavKey) => void
  newPlanOpen: boolean
  openNewPlan: () => void
  closeNewPlan: () => void
  draft: NewPlanDraft
  setDraft: (patch: Partial<NewPlanDraft>) => void
  conversation: ConversationPublic | null
  inspirations: InspirationPublic[]
  inspirationsError: string | null
  creating: boolean
  createError: string | null
  submitNewPlan: () => Promise<boolean>
  sidebarCollapsed: boolean
  toggleSidebarCollapsed: () => void
  mobileSidebarOpen: boolean
  setMobileSidebarOpen: (open: boolean) => void
  mobileRightOpen: boolean
  setMobileRightOpen: (open: boolean) => void
  isMock: boolean
}

const emptyDraft = (): NewPlanDraft => ({
  destination_text: '',
  when_text: '',
  adults_text: '',
  children_text: '',
  budget_text: '',
  pace: null,
  wish_text: '',
})

const AppContext = createContext<AppContextValue | null>(null)

function parseDuration(whenText: string): { duration_days?: number; date_month?: string } {
  const trimmed = whenText.trim()
  if (!trimmed) return {}
  const dayMatch = trimmed.match(/(\d+)\s*天/)
  if (dayMatch) {
    const days = Number(dayMatch[1])
    if (days >= 1) return { duration_days: Math.min(days, 14) }
  }
  const monthMatch = trimmed.match(/(\d{1,2})\s*月/)
  if (monthMatch) return { date_month: monthMatch[1] }
  return {}
}

function parseCount(text: string): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const match = trimmed.match(/(\d+)/)
  if (!match) return null
  return Number(match[1])
}

function parseBudget(text: string): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const normalized = trimmed.replace(/[,，]/g, '').replace(/万/g, '0000')
  const match = normalized.match(/(\d+(\.\d+)?)/)
  if (!match) return null
  return Number(match[1])
}

function draftToPayload(draft: NewPlanDraft): ConversationCreate {
  const destination = draft.destination_text.trim()
  const adults = parseCount(draft.adults_text)
  const children = parseCount(draft.children_text)
  const budget = parseBudget(draft.budget_text)
  const when = parseDuration(draft.when_text)
  const wish = draft.wish_text.trim()
  return {
    destination_text: destination || null,
    destination_city: destination || null,
    duration_days: when.duration_days ?? null,
    date_month: when.date_month ?? null,
    adults,
    children,
    budget_amount_cny: budget,
    pace: draft.pace,
    wish_text: wish || null,
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [nav, setNav] = useState<NavKey>('chat')
  const [newPlanOpen, setNewPlanOpen] = useState(false)
  const [draft, setDraftState] = useState<NewPlanDraft>(emptyDraft)
  const [conversation, setConversation] = useState<ConversationPublic | null>(null)
  const [inspirations, setInspirations] = useState<InspirationPublic[]>(CURRENT_INSPIRATIONS)
  const [inspirationsError, setInspirationsError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [mobileRightOpen, setMobileRightOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    listInspirations()
      .then((items) => {
        if (cancelled) return
        if (items.length > 0) setInspirations(items)
      })
      .catch(() => {
        if (cancelled) return
        setInspirations(CURRENT_INSPIRATIONS)
        setInspirationsError(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const setDraft = useCallback((patch: Partial<NewPlanDraft>) => {
    setDraftState((current) => ({ ...current, ...patch }))
  }, [])

  const openNewPlan = useCallback(() => {
    setCreateError(null)
    setNewPlanOpen(true)
    setMobileSidebarOpen(false)
  }, [])

  const closeNewPlan = useCallback(() => {
    setNewPlanOpen(false)
  }, [])

  const submitNewPlan = useCallback(async () => {
    setCreating(true)
    setCreateError(null)
    try {
      const created = await createConversation(draftToPayload(draft))
      setConversation(created)
      setNewPlanOpen(false)
      setNav('chat')
      navigate('/')
      return true
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建失败，请再试一次'
      setCreateError(message)
      return false
    } finally {
      setCreating(false)
    }
  }, [draft, navigate])

  const value = useMemo<AppContextValue>(
    () => ({
      nav,
      setNav,
      newPlanOpen,
      openNewPlan,
      closeNewPlan,
      draft,
      setDraft,
      conversation,
      inspirations,
      inspirationsError,
      creating,
      createError,
      submitNewPlan,
      sidebarCollapsed,
      toggleSidebarCollapsed: () => setSidebarCollapsed((open) => !open),
      mobileSidebarOpen,
      setMobileSidebarOpen,
      mobileRightOpen,
      setMobileRightOpen,
      isMock: isMockMode,
    }),
    [
      nav,
      newPlanOpen,
      openNewPlan,
      closeNewPlan,
      draft,
      setDraft,
      conversation,
      inspirations,
      inspirationsError,
      creating,
      createError,
      submitNewPlan,
      sidebarCollapsed,
      mobileSidebarOpen,
      mobileRightOpen,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

// Provider 与消费 hook 同文件，供工作台共享状态。
// eslint-disable-next-line react-refresh/only-export-components
export function useApp(): AppContextValue {
  const value = useContext(AppContext)
  if (!value) {
    throw new Error('useApp 必须在 AppProvider 内使用')
  }
  return value
}
