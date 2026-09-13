import api from './api'
import type { ApiEnvelope } from '../types/api'
import type { InspirationPublic } from '../types/inspiration'

export async function listInspirations(): Promise<InspirationPublic[]> {
  const response = await api.get<ApiEnvelope<InspirationPublic[]>>('/inspirations')
  return response.data.data ?? []
}
