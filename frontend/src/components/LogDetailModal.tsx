import { useEffect } from 'react'
import type { ActivityLogEntry } from '../hooks/usePlanningEvents'

function sanitize(text: string): string {
  return text
    .replace(/sk-[A-Za-z0-9_-]+/g, '[已隐藏]')
    .replace(/Bearer\s+\S+/gi, 'Bearer [已隐藏]')
    .replace(/(api[_-]?key|authorization|security[_-]?js[_-]?code|key)[=:]\s*["']?\S+/gi, '$1=[已隐藏]')
    .replace(/https?:\/\/\S+/gi, '[已隐藏链接]')
    .replace(/\b(GET|POST|PUT|PATCH|DELETE)\s+\/\S+/gi, '[已隐藏请求]')
}

export function LogDetailModal({
  entry,
  onClose,
}: {
  entry: ActivityLogEntry | null
  onClose: () => void
}) {
  useEffect(() => {
    if (!entry) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [entry, onClose])

  if (!entry) return null

  const heading = sanitize(entry.detail?.heading || entry.title) || '这一步的说明'
  const rawBody = sanitize(entry.detail?.body || '')
  const body = rawBody || (entry.clickable ? '已脱敏，不展示密钥或原始请求。' : '这一步没有更多摘要。')

  return (
    <div className="overlay" onClick={onClose} role="presentation">
      <div
        className="modal log-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="log-detail-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="log-detail-title">{heading}</h2>
        <pre className="log-detail-body">{body}</pre>
        <div className="modal-actions">
          <button type="button" className="cta-btn" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
