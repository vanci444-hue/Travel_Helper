import { useEffect, useState } from 'react'
import type { ActivityLogEntry } from '../hooks/usePlanningEvents'

function countByTitle(entries: ActivityLogEntry[], pattern: RegExp): number {
  return entries.filter((item) => item.kind === 'tool' && pattern.test(item.title)).length
}

export function ActivityLog({
  entries,
  running,
  onStepClick,
}: {
  entries: ActivityLogEntry[]
  running: boolean
  onStepClick: (entry: ActivityLogEntry) => void
}) {
  const [open, setOpen] = useState(true)

  useEffect(() => {
    if (running) setOpen(true)
  }, [running])

  const placeCount = countByTitle(entries, /搜索|查询城市|查看地点|地理编码|景点/)
  const routeCount = countByTitle(entries, /公交|步行|路线/)
  const failed = entries.some((item) => item.title.includes('未完成'))
  const summary = running
    ? placeCount + routeCount > 0
      ? `规划中 · 已查 ${placeCount} 处地点、${routeCount} 次路线`
      : entries.length
        ? `规划中 · 已记录 ${entries.length} 步`
        : '规划中 · 专员开始工作'
    : failed
      ? `规划未完成 · ${entries.length} 步`
      : placeCount + routeCount > 0
        ? `规划完成 · 已查 ${placeCount} 处地点、${routeCount} 次路线`
        : `规划完成 · ${entries.length} 步`

  return (
    <div className={`activity-log${open ? '' : ' is-fold'}`}>
      <button
        type="button"
        className="activity-log-head"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="activity-chev" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        {summary}
      </button>
      {open ? (
        <div className="activity-log-body">
          {entries.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={`activity-step${entry.clickable ? ' is-clickable' : ''}`}
              onClick={() => {
                if (entry.clickable) onStepClick(entry)
              }}
              disabled={!entry.clickable}
            >
              {entry.kind === 'tool' ? '🔧 ' : entry.kind === 'thought' ? '💭 ' : '👤 '}
              {entry.title}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
