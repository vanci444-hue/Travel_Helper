export interface ApiEnvelope<T> {
  success: boolean
  data: T | null
  error: string | null
  error_code: string | null
  message: string | null
  timestamp: string
  request_id: string
  metadata: Record<string, unknown>
}

export interface MockHttpResult<T = unknown> {
  status: number
  body: ApiEnvelope<T>
}

export function makeEnvelope<T>(
  data: T,
  extras?: Partial<Omit<ApiEnvelope<T>, 'data'>>,
): ApiEnvelope<T> {
  return {
    success: true,
    data,
    error: null,
    error_code: null,
    message: 'ok',
    timestamp: new Date().toISOString(),
    request_id: `req_mock_${crypto.randomUUID()}`,
    metadata: {},
    ...extras,
  }
}

export function makeErrorEnvelope(
  error: string,
  errorCode: string,
): ApiEnvelope<null> {
  return {
    success: false,
    data: null,
    error,
    error_code: errorCode,
    message: null,
    timestamp: new Date().toISOString(),
    request_id: `req_mock_${crypto.randomUUID()}`,
    metadata: {},
  }
}
