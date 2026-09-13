import { makeEnvelope, makeErrorEnvelope, type MockHttpResult } from '../types/api'
import type {
  CompanionType,
  ConversationPublic,
  IntakePublic,
  MessagePublic,
  Pace,
  PlanningPublic,
  PlanningStatus,
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

export interface MessageTurnPublic {
  user_message: MessagePublic
  assistant_message: MessagePublic
  intake: IntakePublic
  planning: PlanningPublic
}

export type PlanningEventName =
  | 'planning.updated'
  | 'planning.log'
  | 'itinerary.ready'
  | 'planning.failed'
  | 'heartbeat'

export type PlanningScenario = 'success' | 'fail'

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

const FAIL_PATTERN = /阿巴|不存在|火星|乱码/
const SUCCESS_ITINERARY_ID = 'itn_mock_01'
const FAIL_REASON = '在国内地图里找不到这个目的地，没有可用的景点信息'
const BUSY_REPLY = '⏳ 专员还在做，完成后会放到行程里。'
const SUCCESS_REPLY = '✨ 方案好了，按天行程在详情页，不贴在对话里。'
const ASK_REPLY =
  '📝 可以。还差几件事就能开工：你从哪座城市出发、玩几天、和谁、预算大概多少、节奏要轻松还是紧凑？专员还不会上场。'
const STUCK_REPLY =
  '📌 还缺出发地或时长等信息，现在不能出假装完整的旅行计划，专员不会上场。'

const EMPTY_SPECIALISTS: SpecialistPublic[] = [
  { role: 'destination_research', status: 'not_started', summary: null },
  { role: 'budget_expert', status: 'not_started', summary: null },
  { role: 'itinerary_design', status: 'not_started', summary: null },
]

const SUCCESS_LOGS: Omit<ActivityLogEntry, 'id' | 'created_at'>[] = [
  {
    kind: 'tool',
    specialist: 'destination_research',
    title: '查询杭州地理编码',
    clickable: true,
    detail: {
      heading: '查询杭州地理编码',
      body: '目的地研究\n结果：杭州市已定位。不展示密钥或原始坐标串。',
    },
  },
  {
    kind: 'tool',
    specialist: 'destination_research',
    title: '搜索景点 西湖',
    clickable: true,
    detail: {
      heading: '搜索景点 西湖',
      body: '找到：西湖、断桥、苏堤。开放时间与适合情侣轻松节奏已记下。',
    },
  },
  {
    kind: 'thought',
    specialist: 'destination_research',
    title: '思考 4s',
    clickable: true,
    detail: {
      heading: '思考 4s',
      body: '先确认湖边点位够不够排 5 天轻松行程，再决定要不要补龙井。',
    },
  },
  {
    kind: 'tool',
    specialist: 'destination_research',
    title: '读取杭州天气',
    clickable: true,
    detail: {
      heading: '读取杭州天气',
      body: '未来几天多云到晴，体感适宜步行。清单里提示轻便外套。',
    },
  },
  {
    kind: 'tool',
    specialist: 'budget_expert',
    title: '估算分类预算',
    clickable: true,
    detail: {
      heading: '估算分类预算',
      body: '交通、住宿、餐饮合计约 1.6 万，未超出 2 万上限。金额为估算。',
    },
  },
  {
    kind: 'tool',
    specialist: 'itinerary_design',
    title: '查询公交 灵隐寺 → 西湖',
    clickable: true,
    detail: {
      heading: '查询公交 灵隐寺 → 西湖',
      body: '公交约 25 分钟。此为摘要，不含完整路线折线，也不含按天方案全文。',
    },
  },
]

const FAIL_LOGS: Omit<ActivityLogEntry, 'id' | 'created_at'>[] = [
  {
    kind: 'tool',
    specialist: 'destination_research',
    title: '查询目的地',
    clickable: true,
    detail: {
      heading: '查询目的地',
      body: '地理编码无结果。国内地图找不到该地名。',
    },
  },
  {
    kind: 'specialist',
    specialist: 'destination_research',
    title: '目的地研究未完成',
    clickable: true,
    detail: {
      heading: '目的地研究未完成',
      body: FAIL_REASON,
    },
  },
]

interface Runtime {
  conversation: ConversationPublic
  scenario: PlanningScenario | null
  streamStarted: boolean
  messageSeq: number
  logSeq: number
}

const store = new Map<string, Runtime>()

function cloneSpecialists(items: SpecialistPublic[]): SpecialistPublic[] {
  return items.map((item) => ({ ...item }))
}

function clonePlanning(planning: PlanningPublic): PlanningPublic {
  return {
    status: planning.status,
    specialists: cloneSpecialists(planning.specialists),
    activity_log: (planning.activity_log as ActivityLogEntry[]).map((entry) => ({
      ...entry,
      detail: entry.detail ? { ...entry.detail } : null,
    })),
    error_message: planning.error_message,
    itinerary_id: planning.itinerary_id,
  }
}

function cloneConversation(conversation: ConversationPublic): ConversationPublic {
  return {
    ...conversation,
    intake: { ...conversation.intake, children_age_bands: [...conversation.intake.children_age_bands], missing_fields: [...conversation.intake.missing_fields] },
    planning: clonePlanning(conversation.planning),
    messages: conversation.messages.map((item) => ({ ...item })),
  }
}

function emptyPlanning(status: PlanningStatus = 'idle'): PlanningPublic {
  return {
    status,
    specialists: cloneSpecialists(EMPTY_SPECIALISTS),
    activity_log: [],
    error_message: null,
    itinerary_id: null,
  }
}

function ensureRuntime(conversation: ConversationPublic): Runtime {
  const existing = store.get(conversation.id)
  if (existing) return existing
  const runtime: Runtime = {
    conversation: cloneConversation({
      ...conversation,
      planning: conversation.planning ?? emptyPlanning(),
      messages: conversation.messages ?? [],
    }),
    scenario: null,
    streamStarted: false,
    messageSeq: conversation.messages.length,
    logSeq: 0,
  }
  store.set(conversation.id, runtime)
  return runtime
}

export function seedPlanningConversation(conversation: ConversationPublic): void {
  ensureRuntime(conversation)
}

export function asActivityLog(value: unknown[] | undefined): ActivityLogEntry[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is ActivityLogEntry => {
    if (!item || typeof item !== 'object') return false
    const entry = item as ActivityLogEntry
    return typeof entry.id === 'string' && typeof entry.title === 'string'
  })
}

function nextMessage(runtime: Runtime, role: MessagePublic['role'], content: string): MessagePublic {
  runtime.messageSeq += 1
  return {
    id: `msg_mock_${String(runtime.messageSeq).padStart(2, '0')}`,
    role,
    display_name: role === 'assistant' ? 'Coco' : '我',
    content,
    created_at: new Date().toISOString(),
  }
}

function nextLog(runtime: Runtime, draft: Omit<ActivityLogEntry, 'id' | 'created_at'>): ActivityLogEntry {
  runtime.logSeq += 1
  return {
    ...draft,
    id: `log_mock_${String(runtime.logSeq).padStart(2, '0')}`,
    created_at: new Date().toISOString(),
  }
}

function missingFieldsOf(intake: IntakePublic): string[] {
  const missing: string[] = []
  if (!intake.origin_city) missing.push('origin_city')
  if (!intake.region) missing.push('region')
  if (!intake.destination_city && !intake.destination_text) missing.push('destination_city')
  if (intake.duration_days == null && !intake.date_month && !intake.date_start) {
    missing.push('duration_days')
  }
  if (intake.adults == null && intake.children == null && !intake.companion_type) {
    missing.push('companion_type')
  }
  if (intake.budget_amount_cny == null && !intake.budget_tier) missing.push('budget_amount_cny')
  if (!intake.pace) missing.push('pace')
  return missing
}

function enrichIntake(intake: IntakePublic, text: string): IntakePublic {
  const next: IntakePublic = {
    ...intake,
    children_age_bands: [...intake.children_age_bands],
    missing_fields: [...intake.missing_fields],
  }

  if (/上海/.test(text)) next.origin_city = next.origin_city || '上海'
  if (/北京/.test(text)) next.origin_city = next.origin_city || '北京'
  if (/杭州/.test(text)) {
    next.destination_city = next.destination_city || '杭州'
    next.destination_text = next.destination_text || '杭州'
    next.region = next.region || 'domestic'
  }
  if (/成都/.test(text)) {
    next.destination_city = next.destination_city || '成都'
    next.destination_text = next.destination_text || '成都'
    next.region = next.region || 'domestic'
  }
  if (/大理/.test(text)) {
    next.destination_city = next.destination_city || '大理'
    next.destination_text = next.destination_text || '大理'
    next.region = next.region || 'domestic'
  }

  const days = text.match(/(\d+)\s*天/)
  if (days) next.duration_days = Number(days[1])
  if (/2\s*万|20000/.test(text)) next.budget_amount_cny = next.budget_amount_cny ?? 20000
  if (/8\s*千|8000/.test(text)) next.budget_amount_cny = next.budget_amount_cny ?? 8000
  if (/不要太赶|轻松/.test(text)) next.pace = next.pace || 'relaxed'
  if (/适中/.test(text)) next.pace = next.pace || 'moderate'
  if (/紧凑|赶/.test(text) && !/不要太赶/.test(text)) next.pace = next.pace || 'packed'
  if (/老婆|配偶|情侣/.test(text)) {
    next.companion_type = next.companion_type || 'couple'
    next.adults = next.adults ?? 2
    next.children = next.children ?? 0
  }
  if (/小孩|亲子|带娃/.test(text)) {
    next.companion_type = next.companion_type || 'parent_child'
    next.children = next.children ?? 1
    next.adults = next.adults ?? 2
  }
  if (/朋友/.test(text)) next.companion_type = next.companion_type || 'friends'
  if (/自己|一个人/.test(text)) {
    next.companion_type = next.companion_type || 'solo'
    next.adults = next.adults ?? 1
  }

  if (FAIL_PATTERN.test(text)) {
    next.origin_city = next.origin_city || '上海'
    next.region = next.region || 'domestic'
    next.destination_text = next.destination_text || text.slice(0, 20)
    next.destination_city = next.destination_city || '未知地点'
    next.duration_days = next.duration_days ?? 3
    next.companion_type = next.companion_type || 'solo'
    next.adults = next.adults ?? 1
    next.children = next.children ?? 0
    next.budget_amount_cny = next.budget_amount_cny ?? 5000
    next.pace = next.pace || 'relaxed'
  }

  next.missing_fields = missingFieldsOf(next)
  next.ready = next.missing_fields.length === 0
  return next
}

function readyReply(intake: IntakePublic): string {
  const dest = intake.destination_city || intake.destination_text || '目的地'
  const days = intake.duration_days ? `${intake.duration_days} 天` : '几天'
  const origin = intake.origin_city || '出发地'
  const budget = intake.budget_amount_cny ? `${intake.budget_amount_cny / 10000} 万` : '已给预算'
  const pace: Record<Pace, string> = { relaxed: '轻松', moderate: '适中', packed: '紧凑' }
  const paceText = intake.pace ? pace[intake.pace] : '已定节奏'
  const who: Record<CompanionType, string> = {
    solo: '一人',
    couple: '情侣',
    family: '家庭',
    friends: '朋友',
    parent_child: '亲子',
    unknown: '同行人',
  }
  const whoText = intake.companion_type ? who[intake.companion_type] : '同行人'
  return `🧭 信息齐了：${origin}出发、${dest} ${days}、${whoText}、${budget}、${paceText}节奏。我这边让专员出一版，你可以在过程里看到进度。`
}

function publicConversation(runtime: Runtime): ConversationPublic {
  return cloneConversation(runtime.conversation)
}

export function getConversationMock(conversationId: string): MockHttpResult<ConversationPublic | null> {
  const runtime = store.get(conversationId)
  if (!runtime) {
    return {
      status: 404,
      body: makeErrorEnvelope('找不到这场对话', 'NOT_FOUND'),
    }
  }
  return {
    status: 200,
    body: makeEnvelope(publicConversation(runtime)),
  }
}

export function sendMessageMock(
  conversationId: string,
  content: string,
): MockHttpResult<MessageTurnPublic | null> {
  const trimmed = content.trim()
  if (!trimmed || trimmed.length > 2000) {
    return {
      status: 400,
      body: makeErrorEnvelope('消息需要 1–2000 字，空格不算有效内容', 'VALIDATION_ERROR'),
    }
  }

  const runtime = store.get(conversationId)
  if (!runtime) {
    return {
      status: 404,
      body: makeErrorEnvelope('找不到这场对话', 'NOT_FOUND'),
    }
  }

  const now = new Date().toISOString()
  const userMessage = nextMessage(runtime, 'user', trimmed)
  runtime.conversation.messages.push(userMessage)
  runtime.conversation.updated_at = now

  if (runtime.conversation.planning.status === 'running') {
    const assistantMessage = nextMessage(runtime, 'assistant', BUSY_REPLY)
    runtime.conversation.messages.push(assistantMessage)
    return {
      status: 200,
      body: makeEnvelope({
        user_message: { ...userMessage },
        assistant_message: { ...assistantMessage },
        intake: { ...runtime.conversation.intake },
        planning: clonePlanning(runtime.conversation.planning),
      }),
    }
  }

  const failIntent = FAIL_PATTERN.test(trimmed)
  const intake = enrichIntake(runtime.conversation.intake, trimmed)
  runtime.conversation.intake = intake

  if (!intake.ready) {
    intake.followup_rounds_used += 1
    const assistantMessage = nextMessage(
      runtime,
      'assistant',
      intake.followup_rounds_used > 2 ? STUCK_REPLY : ASK_REPLY,
    )
    runtime.conversation.messages.push(assistantMessage)
    runtime.conversation.planning = emptyPlanning('idle')
    runtime.scenario = null
    return {
      status: 200,
      body: makeEnvelope({
        user_message: { ...userMessage },
        assistant_message: { ...assistantMessage },
        intake: { ...intake },
        planning: clonePlanning(runtime.conversation.planning),
      }),
    }
  }

  runtime.scenario = failIntent ? 'fail' : 'success'
  runtime.streamStarted = false
  runtime.conversation.planning = {
    status: 'running',
    specialists: [
      { role: 'destination_research', status: 'running', summary: failIntent ? '正在检索目的地' : '正在查点位与天气' },
      { role: 'budget_expert', status: 'not_started', summary: null },
      { role: 'itinerary_design', status: 'not_started', summary: null },
    ],
    activity_log: [],
    error_message: null,
    itinerary_id: null,
  }
  if (runtime.conversation.title === '新对话' && intake.destination_city && intake.duration_days) {
    runtime.conversation.title = `${intake.destination_city} ${intake.duration_days} 天`
  }

  const assistantMessage = nextMessage(
    runtime,
    'assistant',
    failIntent ? '信息够了，我先让专员查这个目的地。过程会写在下面的日志里。' : readyReply(intake),
  )
  runtime.conversation.messages.push(assistantMessage)

  return {
    status: 200,
    body: makeEnvelope({
      user_message: { ...userMessage },
      assistant_message: { ...assistantMessage },
      intake: { ...intake },
      planning: clonePlanning(runtime.conversation.planning),
    }),
  }
}

export function appendPlanningLog(conversationId: string, draft: Omit<ActivityLogEntry, 'id' | 'created_at'>): ActivityLogEntry | null {
  const runtime = store.get(conversationId)
  if (!runtime) return null
  const entry = nextLog(runtime, draft)
  const logs = asActivityLog(runtime.conversation.planning.activity_log)
  logs.push(entry)
  runtime.conversation.planning.activity_log = logs
  runtime.conversation.updated_at = entry.created_at
  return entry
}

export function applyPlanningUpdated(
  conversationId: string,
  patch: { status?: PlanningStatus; specialists: SpecialistPublic[]; itinerary_id?: string | null },
): PlanningPublic | null {
  const runtime = store.get(conversationId)
  if (!runtime) return null
  if (patch.status) runtime.conversation.planning.status = patch.status
  runtime.conversation.planning.specialists = cloneSpecialists(patch.specialists)
  if (patch.itinerary_id !== undefined) runtime.conversation.planning.itinerary_id = patch.itinerary_id
  runtime.conversation.updated_at = new Date().toISOString()
  return clonePlanning(runtime.conversation.planning)
}

export function completePlanningSuccess(conversationId: string): ItineraryReadyPayload | null {
  const runtime = store.get(conversationId)
  if (!runtime) return null
  if (runtime.conversation.planning.status === 'succeeded' && runtime.conversation.planning.itinerary_id) {
    return {
      status: 'succeeded',
      itinerary_id: runtime.conversation.planning.itinerary_id,
      specialists: cloneSpecialists(runtime.conversation.planning.specialists),
    }
  }
  const specialists: SpecialistPublic[] = [
    { role: 'destination_research', status: 'succeeded', summary: '点位与天气可用' },
    { role: 'budget_expert', status: 'succeeded', summary: '合计约 1.6 万，未超上限' },
    { role: 'itinerary_design', status: 'succeeded', summary: '行程已汇总' },
  ]
  runtime.conversation.planning.status = 'succeeded'
  runtime.conversation.planning.specialists = specialists
  runtime.conversation.planning.itinerary_id = SUCCESS_ITINERARY_ID
  runtime.conversation.planning.error_message = null
  const coco = nextMessage(runtime, 'assistant', SUCCESS_REPLY)
  runtime.conversation.messages.push(coco)
  runtime.conversation.updated_at = coco.created_at
  return {
    status: 'succeeded',
    itinerary_id: SUCCESS_ITINERARY_ID,
    specialists,
  }
}

export function completePlanningFailure(conversationId: string): PlanningFailedPayload | null {
  const runtime = store.get(conversationId)
  if (!runtime) return null
  if (runtime.conversation.planning.status === 'failed') {
    const coco = [...runtime.conversation.messages].reverse().find((item) => item.role === 'assistant')
    return {
      status: 'failed',
      itinerary_id: null,
      failure_reason: runtime.conversation.planning.error_message || FAIL_REASON,
      coco_message_id: coco?.id ?? '',
      specialists: cloneSpecialists(runtime.conversation.planning.specialists),
    }
  }
  const specialists: SpecialistPublic[] = [
    { role: 'destination_research', status: 'failed', summary: '地理编码无结果' },
    { role: 'budget_expert', status: 'not_started', summary: null },
    { role: 'itinerary_design', status: 'not_started', summary: null },
  ]
  runtime.conversation.planning.status = 'failed'
  runtime.conversation.planning.specialists = specialists
  runtime.conversation.planning.itinerary_id = null
  runtime.conversation.planning.error_message = FAIL_REASON
  const coco = nextMessage(runtime, 'assistant', `🌫️ 这次没法帮你出方案。原因是：${FAIL_REASON}。你可以换一个国内城市，或者说得更具体一点再试。`)
  runtime.conversation.messages.push(coco)
  runtime.conversation.updated_at = coco.created_at
  return {
    status: 'failed',
    itinerary_id: null,
    failure_reason: FAIL_REASON,
    coco_message_id: coco.id,
    specialists,
  }
}

export function getPlanningScenario(conversationId: string): PlanningScenario | null {
  return store.get(conversationId)?.scenario ?? null
}

export function markPlanningStreamStarted(conversationId: string): boolean {
  const runtime = store.get(conversationId)
  if (!runtime || runtime.streamStarted) return false
  runtime.streamStarted = true
  return true
}

export function releasePlanningStream(conversationId: string): void {
  const runtime = store.get(conversationId)
  if (runtime && runtime.conversation.planning.status === 'running') {
    runtime.streamStarted = false
  }
}

export class PlanningMockEventSource extends EventTarget {
  readonly CONNECTING = 0
  readonly OPEN = 1
  readonly CLOSED = 2
  readyState = 1
  url: string
  withCredentials = false
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onopen: ((event: Event) => void) | null = null
  private timers: number[] = []

  constructor(url: string) {
    super()
    this.url = url
    queueMicrotask(() => {
      if (this.readyState === this.CLOSED) return
      this.dispatchEvent(new Event('open'))
      this.onopen?.(new Event('open'))
    })
  }

  close(): void {
    this.readyState = this.CLOSED
    this.timers.forEach((id) => window.clearTimeout(id))
    this.timers = []
  }

  schedule(delayMs: number, type: PlanningEventName, payload: () => unknown): void {
    const id = window.setTimeout(() => {
      if (this.readyState === this.CLOSED) return
      const data = payload()
      if (data == null) return
      const event = new MessageEvent(type, { data: JSON.stringify(data) })
      this.dispatchEvent(event)
      this.onmessage?.(event)
    }, delayMs)
    this.timers.push(id)
  }
}

export function startPlanningMockStream(conversationId: string): PlanningMockEventSource {
  const source = new PlanningMockEventSource(`/api/conversations/${conversationId}/events`)
  const first = markPlanningStreamStarted(conversationId)
  if (!first) {
    source.close()
    return source
  }

  const scenario = getPlanningScenario(conversationId) ?? 'success'
  const existingTitles = new Set(
    asActivityLog(store.get(conversationId)?.conversation.planning.activity_log).map((item) => item.title),
  )
  const drafts = (scenario === 'fail' ? FAIL_LOGS : SUCCESS_LOGS).filter((item) => !existingTitles.has(item.title))
  let delay = drafts.length === 0 ? 80 : 280

  drafts.forEach((draft) => {
    const at = delay
    source.schedule(at, 'planning.log', () => {
      const entry = appendPlanningLog(conversationId, draft)
      return entry ? { entry } : null
    })
    delay += 280
  })

  if (scenario === 'fail') {
    source.schedule(delay, 'planning.updated', () => {
      const specialists: SpecialistPublic[] = [
        { role: 'destination_research', status: 'failed', summary: '地理编码无结果' },
        { role: 'budget_expert', status: 'not_started', summary: null },
        { role: 'itinerary_design', status: 'not_started', summary: null },
      ]
      applyPlanningUpdated(conversationId, { status: 'running', specialists })
      return { status: 'running', specialists, itinerary_id: null }
    })
    source.schedule(delay + 80, 'planning.failed', () => completePlanningFailure(conversationId))
  } else {
    source.schedule(delay, 'planning.updated', () => {
      const specialists: SpecialistPublic[] = [
        { role: 'destination_research', status: 'succeeded', summary: '已收集西湖、灵隐等点位' },
        { role: 'budget_expert', status: 'running', summary: null },
        { role: 'itinerary_design', status: 'running', summary: null },
      ]
      applyPlanningUpdated(conversationId, { status: 'running', specialists })
      return { status: 'running', specialists, itinerary_id: null }
    })
    source.schedule(delay + 120, 'itinerary.ready', () => completePlanningSuccess(conversationId))
  }

  return source
}

export function planningEventUrl(conversationId: string): string {
  const base = import.meta.env.VITE_API_BASE_URL || '/api'
  return `${base.replace(/\/+$/, '')}/conversations/${conversationId}/events`
}
