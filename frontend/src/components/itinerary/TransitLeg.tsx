import type { TransitLegPublic } from '../../services/itineraryService'
import { TRANSIT_MARK } from '../../ui/travelMarks'

export function TransitLeg({ leg }: { leg: TransitLegPublic }) {
  const text =
    leg.source === 'estimate' && !leg.summary.includes('估算')
      ? `${leg.summary}（估算）`
      : leg.summary
  return (
    <div className="transit-leg">
      <span className="ui-mark" aria-hidden="true">
        {TRANSIT_MARK[leg.mode]}
      </span>
      {text}
    </div>
  )
}
