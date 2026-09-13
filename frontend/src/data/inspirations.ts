import type { InspirationPublic } from '../types/inspiration'

/** 当前版本右栏固定展示的国内灵感，不作为 Mock 角标。 */
export const CURRENT_INSPIRATIONS: InspirationPublic[] = [
  {
    id: 'insp_hangzhou',
    city: '杭州',
    title: '西湖边慢慢走',
    description: '湖景、茶、短途高铁都合适，适合轻松几天。',
    image_url: '/inspirations/hangzhou.jpg',
  },
  {
    id: 'insp_chengdu',
    city: '成都',
    title: '熊猫与火锅',
    description: '节奏可以很慢，吃和逛都适合情侣或家庭。',
    image_url: '/inspirations/chengdu.jpg',
  },
  {
    id: 'insp_dali',
    city: '大理',
    title: '风大，适合发呆',
    description: '洱海边发呆就够了，不要把行程排太满。',
    image_url: '/inspirations/dali.jpg',
  },
]
