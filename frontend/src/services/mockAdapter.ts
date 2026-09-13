import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { createConversationMock } from '../mocks/conversations'
import { listInspirationsMock } from '../mocks/inspirations'
import type { ApiEnvelope, MockHttpResult } from '../types/api'
import type { ConversationCreate } from '../types/conversation'

function requestPath(config: InternalAxiosRequestConfig): string {
  const joined = `${config.baseURL ?? ''}${config.url ?? ''}`
  const withoutOrigin = joined.replace(/^https?:\/\/[^/]+/i, '')
  const [path] = withoutOrigin.split('?')
  return path.replace(/\/+$/, '') || '/'
}

function parseBody(data: unknown): ConversationCreate {
  if (data == null || data === '') return {}
  if (typeof data === 'string') {
    try {
      return JSON.parse(data) as ConversationCreate
    } catch {
      return {}
    }
  }
  return data as ConversationCreate
}

export function dispatchMock(config: InternalAxiosRequestConfig): MockHttpResult {
  const method = (config.method ?? 'get').toLowerCase()
  const path = requestPath(config)

  if (method === 'get' && (path === '/api/inspirations' || path === '/inspirations')) {
    return listInspirationsMock()
  }

  if (method === 'post' && (path === '/api/conversations' || path === '/conversations')) {
    return createConversationMock(parseBody(config.data))
  }

  return {
    status: 404,
    body: {
      success: false,
      data: null,
      error: '接口尚未接入 Mock',
      error_code: 'NOT_FOUND',
      message: null,
      timestamp: new Date().toISOString(),
      request_id: `req_mock_${crypto.randomUUID()}`,
      metadata: {},
    },
  }
}

export async function mockAdapter(config: InternalAxiosRequestConfig): Promise<AxiosResponse> {
  const result = dispatchMock(config)
  const response: AxiosResponse<ApiEnvelope<unknown>> = {
    data: result.body,
    status: result.status,
    statusText: result.status >= 400 ? 'Error' : 'OK',
    headers: { 'content-type': 'application/json' },
    config,
    request: {},
  }
  if (result.status >= 400) {
    throw new AxiosError(
      result.body.error || 'Request failed',
      AxiosError.ERR_BAD_RESPONSE,
      config,
      {},
      response,
    )
  }
  return response
}
