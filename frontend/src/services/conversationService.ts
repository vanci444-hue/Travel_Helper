import { AxiosError } from 'axios'
import api, { isMockMode } from './api'
import {
  getConversationMock,
  seedPlanningConversation,
  sendMessageMock,
  type MessageTurnPublic,
} from '../mocks/planning'
import type { ApiEnvelope } from '../types/api'
import type { ConversationCreate, ConversationPublic } from '../types/conversation'

/** API-001 预填后立刻走 API-004，避免经理重问已填项（AC-014）。 */
export const CONTINUE_AFTER_CREATE = '请根据已填写的计划继续，不要重复已给的字段。'

function unwrapError(error: unknown, fallback: string): Error {
  if (error instanceof AxiosError) {
    const body = error.response?.data as ApiEnvelope<null> | undefined
    return new Error(body?.error || fallback)
  }
  if (error instanceof Error) return error
  return new Error(fallback)
}

function throwIfMockFailed<T>(result: { status: number; body: ApiEnvelope<T | null> }, fallback: string): T {
  if (result.status >= 400 || !result.body.data) {
    throw new Error(result.body.error || fallback)
  }
  return result.body.data
}

function hasPrefill(payload: ConversationCreate): boolean {
  const values: unknown[] = [
    payload.origin_city,
    payload.region,
    payload.destination_text,
    payload.destination_city,
    payload.duration_days,
    payload.date_start,
    payload.date_end,
    payload.date_month,
    payload.companion_type,
    payload.adults,
    payload.children,
    payload.children_age_bands?.length ? payload.children_age_bands : null,
    payload.budget_amount_cny,
    payload.budget_tier,
    payload.pace,
    payload.wish_text,
  ]
  return values.some((value) => value !== undefined && value !== null && value !== '')
}

function mergeTurn(created: ConversationPublic, turn: MessageTurnPublic): ConversationPublic {
  return {
    ...created,
    messages: [...created.messages, turn.user_message, turn.assistant_message],
    intake: turn.intake,
    planning: turn.planning,
    updated_at: turn.assistant_message.created_at,
  }
}

export async function createConversation(
  payload: ConversationCreate,
): Promise<ConversationPublic> {
  try {
    const response = await api.post<ApiEnvelope<ConversationPublic>>('/conversations', payload)
    if (!response.data.data) {
      throw new Error(response.data.error || '新建对话失败')
    }
    const created = response.data.data
    if (isMockMode) seedPlanningConversation(created)
    if (isMockMode || !hasPrefill(payload)) return created

    const turn = await sendMessage(created.id, CONTINUE_AFTER_CREATE)
    try {
      return await getConversation(created.id)
    } catch {
      return mergeTurn(created, turn)
    }
  } catch (error) {
    throw unwrapError(error, '新建对话失败')
  }
}

export async function getConversation(conversationId: string): Promise<ConversationPublic> {
  if (isMockMode) {
    return throwIfMockFailed(getConversationMock(conversationId), '找不到这场对话')
  }
  try {
    const response = await api.get<ApiEnvelope<ConversationPublic>>(`/conversations/${conversationId}`)
    if (!response.data.data) {
      throw new Error(response.data.error || '找不到这场对话')
    }
    return response.data.data
  } catch (error) {
    throw unwrapError(error, '找不到这场对话')
  }
}

/** 与规划看门狗对齐，修订/问诊同步等模型，不能用默认 15s 或问诊 30s 掐断。 */
export const SEND_MESSAGE_TIMEOUT_MS = 180_000

export async function sendMessage(
  conversationId: string,
  content: string,
): Promise<MessageTurnPublic> {
  if (isMockMode) {
    return throwIfMockFailed(sendMessageMock(conversationId, content), '发送失败')
  }
  try {
    const response = await api.post<ApiEnvelope<MessageTurnPublic>>(
      `/conversations/${conversationId}/messages`,
      { content },
      { timeout: SEND_MESSAGE_TIMEOUT_MS },
    )
    if (!response.data.data) {
      throw new Error(response.data.error || 'Coco 暂时没有回复，请再试一次')
    }
    return response.data.data
  } catch (error) {
    throw unwrapError(error, 'Coco 暂时没有回复，请再试一次')
  }
}

export type { MessageTurnPublic }
