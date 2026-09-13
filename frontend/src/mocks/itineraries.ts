import { makeEnvelope, makeErrorEnvelope, type ApiEnvelope, type MockHttpResult } from '../types/api'
// Mock 内存库随模块重载重置。
import type { Pace } from '../types/conversation'
import type {
  ItineraryCardPublic,
  ItineraryDayPublic,
  ItineraryListItem,
  ItineraryPublic,
  PaginationPublic,
  TransitLegPublic,
} from '../services/itineraryService'

type InternalStatus = 'ready' | 'planning'

interface ItineraryEntity {
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
  budget: ItineraryPublic['budget']
  checklist: ItineraryPublic['checklist']
  map_center: ItineraryPublic['map_center']
  quick_suggestions: ItineraryPublic['quick_suggestions']
  status: InternalStatus
  created_at: string
  updated_at: string
}

interface PaginatedMock<T> extends MockHttpResult<T> {
  body: ApiEnvelope<T> & { pagination: PaginationPublic }
}

const NOW = new Date().toISOString()

function card(
  partial: ItineraryCardPublic,
): ItineraryCardPublic {
  return {
    id: partial.id,
    type: partial.type,
    title: partial.title,
    poi_id: partial.poi_id,
    lng: partial.lng,
    lat: partial.lat,
    address: partial.address,
    intro: partial.intro,
    photo_url: partial.photo_url,
    start_time: partial.start_time,
    suitable_for_children: partial.suitable_for_children,
  }
}

function leg(summary: string, mode: TransitLegPublic['mode'], minutes: number, source: TransitLegPublic['source']): TransitLegPublic {
  return {
    mode,
    duration_min: minutes,
    distance_m: null,
    summary,
    source,
  }
}

function toListItem(entity: ItineraryEntity): ItineraryListItem {
  return {
    id: entity.id,
    title: entity.title,
    destination_city: entity.destination_city,
    duration_days: entity.duration_days,
    pace: entity.pace,
    updated_at: entity.updated_at,
    conversation_id: entity.conversation_id,
  }
}

function toPublic(entity: ItineraryEntity): ItineraryPublic {
  return {
    id: entity.id,
    conversation_id: entity.conversation_id,
    title: entity.title,
    destination_city: entity.destination_city,
    origin_city: entity.origin_city,
    duration_days: entity.duration_days,
    pace: entity.pace,
    companion_type: entity.companion_type,
    assumptions: [...entity.assumptions],
    days: entity.days.map((day) => ({
      day_index: day.day_index,
      label: day.label,
      date: day.date,
      cards: day.cards.map((item) => ({ ...item })),
      legs: day.legs.map((item) => ({ ...item })),
    })),
    budget: {
      currency: entity.budget.currency,
      cap_amount: entity.budget.cap_amount,
      total_amount: entity.budget.total_amount,
      over_cap: entity.budget.over_cap,
      includes_note: entity.budget.includes_note,
      categories: entity.budget.categories.map((item) => ({ ...item })),
    },
    checklist: entity.checklist.map((item) => ({ ...item })),
    map_center: { ...entity.map_center },
    quick_suggestions: entity.quick_suggestions.slice(0, 4).map((item) => ({ ...item })),
    status: 'ready',
    created_at: entity.created_at,
    updated_at: entity.updated_at,
  }
}

function rebuildLegs(day: ItineraryDayPublic): TransitLegPublic[] {
  if (day.cards.length < 2) return []
  if (day.legs.length === day.cards.length - 1) {
    return day.legs.slice(0, day.cards.length - 1).map((item) => ({ ...item }))
  }
  const next: TransitLegPublic[] = []
  for (let index = 0; index < day.cards.length - 1; index += 1) {
    next.push(day.legs[index] ?? leg('约 15 分钟（估算）', 'mixed', 15, 'estimate'))
  }
  return next
}

function makeHangzhou(): ItineraryEntity {
  const days: ItineraryDayPublic[] = [
    {
      day_index: 1,
      label: '第 1 天',
      date: null,
      cards: [
        card({
          id: 'card_d1_01',
          type: 'attraction',
          title: '灵隐寺',
          poi_id: 'B023B0XXXX',
          lng: 120.101,
          lat: 30.241,
          address: '杭州市西湖区法云弄1号',
          intro: '香火与山林，适合慢慢走，不要排在午后最赶的一段。',
          photo_url: null,
          start_time: '10:00',
          suitable_for_children: true,
        }),
        card({
          id: 'card_d1_02',
          type: 'attraction',
          title: '西湖',
          poi_id: 'B0FFFAB6J2',
          lng: 120.148,
          lat: 30.242,
          address: '杭州市西湖区',
          intro: '杭州核心湖区，适合轻松散步。轻松节奏每天大约 1–2 个主要点。',
          photo_url: null,
          start_time: '14:00',
          suitable_for_children: true,
        }),
      ],
      legs: [leg('公交约 25 分钟', 'transit', 25, 'amap')],
    },
    {
      day_index: 2,
      label: '第 2 天',
      date: null,
      cards: [
        card({
          id: 'card_d2_01',
          type: 'attraction',
          title: '龙井村',
          poi_id: 'B023B08K2N',
          lng: 120.116,
          lat: 30.22,
          address: '杭州市西湖区龙井路',
          intro: '茶田与步行，情侣轻松行程。',
          photo_url: null,
          start_time: '10:00',
          suitable_for_children: true,
        }),
        card({
          id: 'card_d2_02',
          type: 'lodging',
          title: '推荐住宿 · 湖边民宿',
          poi_id: null,
          lng: 120.155,
          lat: 30.228,
          address: '南山路附近',
          intro: '仅推荐，不代订、不展示支出。',
          photo_url: null,
          start_time: null,
          suitable_for_children: true,
        }),
      ],
      legs: [leg('步行约 12 分钟', 'walking', 12, 'estimate')],
    },
    {
      day_index: 3,
      label: '第 3 天',
      date: null,
      cards: [
        card({
          id: 'card_d3_01',
          type: 'attraction',
          title: '西溪湿地',
          poi_id: 'B023B05189',
          lng: 120.063,
          lat: 30.274,
          address: '杭州市西湖区天目山路518号',
          intro: '留白较多的一天，适合把节奏再放慢。',
          photo_url: null,
          start_time: '10:30',
          suitable_for_children: true,
        }),
        card({
          id: 'card_d3_02',
          type: 'attraction',
          title: '河坊街',
          poi_id: 'B023B06N2P',
          lng: 120.169,
          lat: 30.245,
          address: '杭州市上城区河坊街',
          intro: '晚上轻松走走，看看小吃与老街。',
          photo_url: null,
          start_time: '17:30',
          suitable_for_children: true,
        }),
      ],
      legs: [leg('公交约 40 分钟', 'transit', 40, 'amap')],
    },
    {
      day_index: 4,
      label: '第 4 天',
      date: null,
      cards: [
        card({
          id: 'card_d4_01',
          type: 'attraction',
          title: '九溪十八涧',
          poi_id: 'B023B08M1Q',
          lng: 120.113,
          lat: 30.205,
          address: '杭州市西湖区九溪路',
          intro: '溪谷散步，轻松节奏不排满。',
          photo_url: null,
          start_time: '10:00',
          suitable_for_children: true,
        }),
      ],
      legs: [],
    },
    {
      day_index: 5,
      label: '第 5 天',
      date: null,
      cards: [
        card({
          id: 'card_d5_01',
          type: 'other',
          title: '湖滨漫步 / 返程',
          poi_id: null,
          lng: 120.165,
          lat: 30.253,
          address: '杭州市西湖区湖滨路',
          intro: '返程前留半天空白，不赶场。',
          photo_url: null,
          start_time: '09:30',
          suitable_for_children: true,
        }),
      ],
      legs: [],
    },
  ]

  return {
    id: 'itn_mock_01',
    conversation_id: 'conv_01',
    title: '杭州 5 日轻松游',
    destination_city: '杭州',
    origin_city: '上海',
    duration_days: 5,
    pace: 'relaxed' as Pace,
    companion_type: 'couple',
    assumptions: ['市内交通按公交+适量步行', '住宿为推荐档，不代订'],
    days,
    budget: {
      currency: 'CNY',
      cap_amount: 20000,
      total_amount: 16200,
      over_cap: false,
      includes_note: '含上海—杭州往返与当地食住行门票的估算，非实时报价',
      categories: [
        { key: 'transport', label: '交通', amount: 4000 },
        { key: 'lodging', label: '住宿', amount: 6000 },
        { key: 'food', label: '餐饮', amount: 3500 },
        { key: 'tickets', label: '门票活动', amount: 2200 },
        { key: 'other', label: '其他', amount: 500 },
      ],
    },
    checklist: [
      { id: 'chk_01', text: '携带身份证', relevant: true },
      { id: 'chk_02', text: '查看是否需要提前预约西湖周边热门园', relevant: true },
      { id: 'chk_03', text: '带一件轻便外套', relevant: true },
      { id: 'chk_04', text: '准备舒适步行鞋', relevant: true },
    ],
    map_center: { lng: 120.15, lat: 30.25 },
    quick_suggestions: [
      { id: 'qs_01', text: '第三天不要排那么满' },
      { id: 'qs_02', text: '白天少走路，多坐公交' },
      { id: 'qs_03', text: '换一家更安静的推荐住宿' },
      { id: 'qs_04', text: '换个目的地，改去成都' },
    ],
    status: 'ready',
    created_at: NOW,
    updated_at: NOW,
  }
}

function makePlanningDraft(): ItineraryEntity {
  return {
    ...makeHangzhou(),
    id: 'itn_planning',
    conversation_id: 'conv_planning',
    title: '成都规划中',
    destination_city: '成都',
    status: 'planning',
  }
}

const store: ItineraryEntity[] = [makeHangzhou(), makePlanningDraft()]

function canonicalItineraryId(itineraryId: string): string {
  return itineraryId === 'itn_01' ? 'itn_mock_01' : itineraryId
}

function paginationOf(totalItems: number, page: number, pageSize: number): PaginationPublic {
  const totalPages = totalItems === 0 ? 0 : Math.ceil(totalItems / pageSize)
  return {
    page,
    page_size: pageSize,
    total_items: totalItems,
    total_pages: totalPages,
    has_next: page < totalPages,
    has_prev: page > 1,
  }
}

export function listItinerariesMock(query: {
  page?: number
  page_size?: number
  empty?: boolean
} = {}): PaginatedMock<ItineraryListItem[]> {
  const page = query.page ?? 1
  const pageSize = Math.min(query.page_size ?? 20, 50)
  const ready = query.empty
    ? []
    : store.filter((item) => item.status === 'ready').map((item) => toListItem(item))
  const start = (page - 1) * pageSize
  const slice = ready.slice(start, start + pageSize)
  return {
    status: 200,
    body: {
      ...makeEnvelope(slice),
      pagination: paginationOf(ready.length, page, pageSize),
    },
  }
}

export function getItineraryMock(itineraryId: string): MockHttpResult<ItineraryPublic | null> {
  const found = store.find((item) => item.id === canonicalItineraryId(itineraryId) && item.status === 'ready')
  if (!found) {
    return {
      status: 404,
      body: makeErrorEnvelope('行程不存在', 'NOT_FOUND'),
    }
  }
  return {
    status: 200,
    body: makeEnvelope(toPublic(found)),
  }
}

export function deleteItineraryCardMock(
  itineraryId: string,
  cardId: string,
): MockHttpResult<ItineraryPublic | null> {
  const found = store.find((item) => item.id === canonicalItineraryId(itineraryId) && item.status === 'ready')
  if (!found) {
    return {
      status: 404,
      body: makeErrorEnvelope('行程不存在', 'NOT_FOUND'),
    }
  }

  let removed = false
  found.days = found.days.map((day) => {
    const nextCards = day.cards.filter((item) => item.id !== cardId)
    if (nextCards.length !== day.cards.length) removed = true
    const nextDay = { ...day, cards: nextCards }
    return { ...nextDay, legs: rebuildLegs(nextDay) }
  })

  if (!removed) {
    return {
      status: 404,
      body: makeErrorEnvelope('卡片不存在', 'NOT_FOUND'),
    }
  }

  found.updated_at = new Date().toISOString()
  return {
    status: 200,
    body: makeEnvelope(toPublic(found)),
  }
}

export function resetItineraryMocks(): void {
  store.splice(0, store.length, makeHangzhou(), makePlanningDraft())
}
