import type { SpecialistPublic, SpecialistRole, SpecialistStatus as SpecialistState } from '../types/conversation'
import { SPECIALIST_MARK } from '../ui/travelMarks'

const ROLE_LABEL: Record<SpecialistRole, string> = {
  destination_research: '目的地研究',
  budget_expert: '预算专家',
  itinerary_design: '行程设计',
}

const STATUS_LABEL: Record<SpecialistState, string> = {
  not_started: '未执行',
  running: '进行中',
  succeeded: '已完成',
  failed: '未完成',
}

export function SpecialistStatus({ specialists }: { specialists: SpecialistPublic[] }) {
  return (
    <ul className="spec-list" aria-label="专员过程">
      {specialists.map((item) => (
        <li key={item.role} className={`spec-row is-${item.status}`}>
          {item.status === 'running' ? <span className="spec-spin" aria-hidden="true" /> : null}
          <span>
            {SPECIALIST_MARK[item.role]} {ROLE_LABEL[item.role]} · {STATUS_LABEL[item.status]}
            {item.summary ? ` · ${item.summary}` : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}
