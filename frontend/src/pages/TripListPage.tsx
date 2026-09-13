import { useNavigate, useSearchParams } from 'react-router'
import { useApp } from '../stores/AppProvider'
import { useTripList } from '../hooks/useItinerary'
import { formatUpdatedAt, PACE_LABEL } from '../services/itineraryService'
import { PACE_MARK } from '../ui/travelMarks'

export function TripListPage() {
  const { isMock } = useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const empty = searchParams.get('empty') === '1'
  const { items, loading, error } = useTripList({ empty })

  return (
    <div className="trip-list">
      <style>{TRIP_LIST_STYLES}</style>
      <div className="trip-list-head">
        <h1>🧳 行程</h1>
        {isMock ? <span className="mock-badge">[Mock]</span> : null}
      </div>
      {loading ? <p className="empty-copy">正在加载行程…</p> : null}
      {error ? <p className="empty-copy">{error}</p> : null}
      {!loading && !error && items.length === 0 ? (
        <p className="empty-copy">✈️ 还没有行程，先和 Coco 聊一趟。</p>
      ) : null}
      {!loading && items.length > 0 ? (
        <div className="trip-rows">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className="trip-row"
              onClick={() => navigate(`/itineraries/${item.id}`)}
            >
              <strong>
                <span className="ui-mark" aria-hidden="true">
                  🗺️
                </span>
                {item.title}
              </strong>
              <span className="trip-meta">
                📍 {item.destination_city} · {item.duration_days} 天 · {PACE_MARK[item.pace]}{' '}
                {PACE_LABEL[item.pace]} · {formatUpdatedAt(item.updated_at)}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

const TRIP_LIST_STYLES = `
.trip-list-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.trip-list-head h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
}
.trip-rows {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
  max-width: 760px;
}
.trip-row {
  display: block;
  width: 100%;
  text-align: left;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  padding: 16px;
  color: var(--text-primary);
}
.trip-row:hover { background: var(--bg-hover); }
.trip-row:active { background: var(--bg-selected); }
.trip-row:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.35);
  outline-offset: 2px;
  border-color: var(--border-strong);
}
.trip-row:disabled { background: var(--bg-elevated); }
.trip-row strong {
  display: block;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.55;
}
.trip-meta {
  display: block;
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.4;
}
`
