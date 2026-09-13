import { CURRENT_INSPIRATIONS } from '../data/inspirations'
import { makeEnvelope, type MockHttpResult } from '../types/api'
import type { InspirationPublic } from '../types/inspiration'

export const inspirationListData: InspirationPublic[] = CURRENT_INSPIRATIONS

export function listInspirationsMock(): MockHttpResult<InspirationPublic[]> {
  return {
    status: 200,
    body: makeEnvelope(
      inspirationListData.map((item) => ({
        id: item.id,
        city: item.city,
        title: item.title,
        description: item.description,
        image_url: item.image_url,
      })),
    ),
  }
}
