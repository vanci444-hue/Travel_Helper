import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useParams } from 'react-router'
import { AppShell } from '../components/layout/AppShell'
import { BudgetPanel } from '../components/itinerary/BudgetPanel'
import { ChecklistPanel } from '../components/itinerary/ChecklistPanel'
import { DayChips } from '../components/itinerary/DayChips'
import { ItineraryCard } from '../components/itinerary/ItineraryCard'
import { MicroDetailModal } from '../components/itinerary/MicroDetailModal'
import { QuickSuggestions } from '../components/itinerary/QuickSuggestions'
import { TransitLeg } from '../components/itinerary/TransitLeg'
import { GlowComposerBox } from '../components/ui/BorderGlow'
import { useItinerary } from '../hooks/useItinerary'
import { useApp } from '../stores/AppProvider'
import {
  isDestinationChange,
  PACE_LABEL,
  type ItineraryCardPublic,
  type MapPointPublic,
} from '../services/itineraryService'
import type { MessagePublic } from '../types/conversation'
import { CARD_TYPE_MARK, PACE_MARK } from '../ui/travelMarks'

interface SideMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

const HELLO_MESSAGE: SideMessage = {
  id: 'side_hello',
  role: 'assistant',
  content: '👋 这份行程可以改某一张卡片，或直接跟我说。',
}

type AMapMap = {
  destroy?: () => void
  add?: (overlay: unknown) => void
  remove?: (overlay: unknown) => void
  setFitView?: (overlays?: unknown[], immediately?: boolean, avoid?: [number, number, number, number]) => void
  setZoomAndCenter?: (zoom: number, center: [number, number]) => void
}
type AMapMarker = { setMap?: (map: AMapMap | null) => void }
type AMapCtor = {
  Map: new (
    container: string | HTMLElement,
    opts: { zoom: number; center: [number, number]; viewMode?: string },
  ) => AMapMap
  Marker: new (opts: {
    position: [number, number]
    title?: string
    label?: { content: string; direction?: string }
  }) => AMapMarker
}

function amapWindow(): {
  _AMapSecurityConfig?: { securityJsCode?: string }
  AMap?: AMapCtor
} {
  return window as typeof window & {
    _AMapSecurityConfig?: { securityJsCode?: string }
    AMap?: AMapCtor
  }
}

function loadAMapScript(key: string): Promise<AMapCtor> {
  const host = amapWindow()
  if (host.AMap) return Promise.resolve(host.AMap)

  const existing = document.querySelector<HTMLScriptElement>('script[data-amap-jsapi="2.0"]')
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => {
        if (host.AMap) resolve(host.AMap)
        else reject(new Error('地图脚本未就绪'))
      })
      existing.addEventListener('error', () => reject(new Error('地图脚本加载失败')))
    })
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`
    script.async = true
    script.dataset.amapJsapi = '2.0'
    script.onload = () => {
      if (host.AMap) resolve(host.AMap)
      else reject(new Error('地图脚本未就绪'))
    }
    script.onerror = () => reject(new Error('地图脚本加载失败'))
    document.head.appendChild(script)
  })
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

function visibleThread(messages: MessagePublic[] | undefined): SideMessage[] {
  return (messages ?? []).flatMap((item) =>
    item.role === 'user' || item.role === 'assistant'
      ? [{ id: item.id, role: item.role, content: item.content }]
      : [],
  )
}

function DayMapPanel({
  center,
  points,
}: {
  center: MapPointPublic
  points: ItineraryCardPublic[]
}) {
  const jsKey = import.meta.env.VITE_AMAP_JS_KEY?.trim() ?? ''
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE?.trim() ?? ''
  const jsKeyConfigured = Boolean(jsKey)
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<AMapMap | null>(null)
  const amapRef = useRef<AMapCtor | null>(null)
  const markersRef = useRef<AMapMarker[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'failed'>(
    jsKeyConfigured ? 'loading' : 'idle',
  )

  useEffect(() => {
    if (!jsKeyConfigured || !containerRef.current) return

    let cancelled = false
    if (securityCode) {
      amapWindow()._AMapSecurityConfig = { securityJsCode: securityCode }
    }

    void loadAMapScript(jsKey)
      .then((AMap) => {
        if (cancelled || !containerRef.current) return
        amapRef.current = AMap
        mapRef.current = new AMap.Map(containerRef.current, {
          zoom: 13,
          center: [center.lng, center.lat],
          viewMode: '2D',
        })
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('failed')
      })

    return () => {
      cancelled = true
      markersRef.current.forEach((marker) => marker.setMap?.(null))
      markersRef.current = []
      mapRef.current?.destroy?.()
      mapRef.current = null
      amapRef.current = null
    }
    // 首次挂载加载一次；换天打点由下面的 markers effect 处理
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jsKey, jsKeyConfigured, securityCode])

  useEffect(() => {
    const map = mapRef.current
    const AMap = amapRef.current
    if (!map || !AMap || status !== 'ready') return

    markersRef.current.forEach((marker) => {
      map.remove?.(marker)
      marker.setMap?.(null)
    })
    markersRef.current = []

    const nextMarkers = points.map(
      (card, index) =>
        new AMap.Marker({
          position: [card.lng as number, card.lat as number],
          title: card.title,
          label: {
            content: `<span class="amap-day-label">${index + 1}. ${escapeHtml(card.title)}</span>`,
            direction: 'top',
          },
        }),
    )
    nextMarkers.forEach((marker) => map.add?.(marker))
    markersRef.current = nextMarkers
    if (nextMarkers.length > 0) {
      map.setFitView?.(nextMarkers, false, [48, 48, 48, 48])
    } else {
      map.setZoomAndCenter?.(13, [center.lng, center.lat])
    }
  }, [center.lat, center.lng, points, status])

  const copy =
    !jsKeyConfigured
      ? '🗺️ 地图未配置'
      : status === 'failed'
        ? '🗺️ 地图暂时无法显示'
        : status === 'ready'
          ? ''
          : '🗺️ 地图加载中'

  return (
    <div className="day-map" aria-label={jsKeyConfigured ? '当天行程地图' : '地图未配置'}>
      {jsKeyConfigured ? <div ref={containerRef} className="day-map-canvas" /> : null}
      {copy ? <p className="map-unconfigured">{copy}</p> : null}
    </div>
  )
}

export function ItineraryDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { isMock, setNav } = useApp()
  const { itinerary, conversation, loading, revising, error, deleteCard, sendRevision } = useItinerary(id)
  const [activeDay, setActiveDay] = useState(1)
  const [mapMode, setMapMode] = useState(false)
  const [detailCard, setDetailCard] = useState<ItineraryCardPublic | null>(null)
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<SideMessage[]>([HELLO_MESSAGE])
  const [showSuggestions, setShowSuggestions] = useState(true)
  const reportRef = useRef<HTMLDivElement>(null)
  const threadRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setNav('trips')
  }, [setNav])

  useEffect(() => {
    if (itinerary?.days[0]) setActiveDay(itinerary.days[0].day_index)
    setShowSuggestions(true)
  }, [itinerary?.id])

  useEffect(() => {
    const history = visibleThread(conversation?.messages)
    setMessages(history.length > 0 ? history : [HELLO_MESSAGE])
  }, [conversation?.id, conversation?.messages])

  useEffect(() => {
    const root = reportRef.current
    if (!root || !itinerary || mapMode) return
    const syncEndSpace = () => {
      root.style.setProperty('--report-end-space', `${root.clientHeight}px`)
    }
    syncEndSpace()
    const resizeObserver = new ResizeObserver(syncEndSpace)
    resizeObserver.observe(root)

    const sections = Array.from(root.querySelectorAll<HTMLElement>('[data-day]'))
    if (sections.length === 0) {
      return () => resizeObserver.disconnect()
    }

    const applyActiveDay = () => {
      const rootRect = root.getBoundingClientRect()
      const bandBottom = rootRect.top + rootRect.height * 0.45
      const candidates = sections
        .map((section) => {
          const rect = section.getBoundingClientRect()
          const visible = Math.max(
            0,
            Math.min(rect.bottom, bandBottom) - Math.max(rect.top, rootRect.top),
          )
          return {
            day: Number(section.getAttribute('data-day')),
            visible,
            top: rect.top - rootRect.top,
          }
        })
        .filter((item) => item.day && item.visible > 0)
      if (candidates.length > 0) {
        candidates.sort((a, b) => b.visible - a.visible || a.top - b.top)
        setActiveDay(candidates[0].day)
        return
      }
      const last = sections[sections.length - 1]
      const lastTop = last.getBoundingClientRect().top - rootRect.top
      const lastDay = Number(last.getAttribute('data-day'))
      if (lastDay && lastTop < 0) setActiveDay(lastDay)
    }

    const observer = new IntersectionObserver(applyActiveDay, {
      root,
      rootMargin: '0px 0px -55% 0px',
      threshold: [0, 0.25, 0.6],
    })
    sections.forEach((section) => observer.observe(section))
    root.addEventListener('scroll', applyActiveDay, { passive: true })
    return () => {
      resizeObserver.disconnect()
      observer.disconnect()
      root.removeEventListener('scroll', applyActiveDay)
    }
  }, [itinerary, mapMode])

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight })
  }, [messages])

  const currentDay = useMemo(
    () => itinerary?.days.find((day) => day.day_index === activeDay) ?? itinerary?.days[0],
    [itinerary, activeDay],
  )
  const mapPoints = useMemo(
    () => (currentDay?.cards ?? []).filter((card) => card.lng != null && card.lat != null),
    [currentDay],
  )

  const scrollToDay = useCallback((dayIndex: number) => {
    setActiveDay(dayIndex)
    const target = reportRef.current?.querySelector<HTMLElement>(`[data-day="${dayIndex}"]`)
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  const pushTurn = useCallback(
    async (userText: string) => {
      const userMessage: SideMessage = {
        id: `side_u_${crypto.randomUUID()}`,
        role: 'user',
        content: userText,
      }
      setShowSuggestions(false)
      setMessages((current) => [...current, userMessage])

      if (isMock) {
        const cocoText = isDestinationChange(userText)
          ? '🗺️ 换目的地这类大改，请去新建计划。当前这份卡片先不动。'
          : '👍 已记下。这是同一份报告，逐项改也走这里。'
        setMessages((current) => [
          ...current,
          { id: `side_a_${crypto.randomUUID()}`, role: 'assistant', content: cocoText },
        ])
        return
      }

      try {
        await sendRevision(userText)
      } catch (caught) {
        setMessages((current) => [
          ...current,
          {
            id: `side_err_${crypto.randomUUID()}`,
            role: 'assistant',
            content: caught instanceof Error ? caught.message : 'Coco 暂时没有回复，请再试一次',
          },
        ])
      }
    },
    [isMock, sendRevision],
  )

  function handleSend(event?: FormEvent) {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || revising) return
    setDraft('')
    void pushTurn(text)
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const main = (
    <div className="detail-layout">
      <style>{DETAIL_STYLES}</style>
      {loading ? <p className="empty-copy detail-status">正在打开行程…</p> : null}
      {error ? (
        <div className="detail-status">
          <p className="empty-copy">{error}</p>
          <Link to="/" className="text-btn">
            回行程列表
          </Link>
        </div>
      ) : null}
      {itinerary ? (
        <>
          <div className="detail-report">
            <header className="detail-report-head">
              <div className="detail-title-row">
                <h1>{itinerary.title}</h1>
                {isMock ? <span className="mock-badge">[Mock]</span> : null}
              </div>
              <p className="detail-sub">
                {PACE_MARK[itinerary.pace]} {PACE_LABEL[itinerary.pace]} · 📍 {itinerary.destination_city}{' '}
                {itinerary.duration_days} 天
              </p>
              <div className="detail-toolbar">
                <DayChips days={itinerary.days} activeDay={activeDay} onSelect={scrollToDay} />
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => setMapMode((open) => !open)}
                >
                  {mapMode ? '📋 返回行程' : '🗺️ 地图模式'}
                </button>
              </div>
            </header>

            <div className="detail-report-body" ref={reportRef}>
            {mapMode ? (
              <section className="map-panel" aria-label="地图模式">
                <DayMapPanel center={itinerary.map_center} points={mapPoints} />
                <ul className="map-card-strip" aria-label="当天地点">
                  {mapPoints.map((card) => (
                    <li key={card.id}>
                      <button type="button" className="map-card-chip" onClick={() => setDetailCard(card)}>
                        {CARD_TYPE_MARK[card.type]} {card.title}
                      </button>
                    </li>
                  ))}
                </ul>
                {mapPoints.length === 0 ? <p className="report-note">当天没有可对应的地点。</p> : null}
              </section>
            ) : (
              <>
                <BudgetPanel budget={itinerary.budget} />
                <ChecklistPanel items={itinerary.checklist} />
                {itinerary.days.map((day) => (
                  <section key={day.day_index} className="day-section" data-day={day.day_index} id={`day-${day.day_index}`}>
                    <h2>
                      <span className="ui-mark" aria-hidden="true">
                        📅
                      </span>
                      {day.label}
                    </h2>
                    {day.cards.map((card, index) => (
                      <div key={card.id}>
                        <ItineraryCard
                          card={card}
                          onOpen={setDetailCard}
                          onDelete={(cardId) => void deleteCard(cardId)}
                        />
                        {index < day.cards.length - 1 && day.legs[index] ? (
                          <TransitLeg leg={day.legs[index]} />
                        ) : null}
                      </div>
                    ))}
                  </section>
                ))}
                <div className="detail-report-end-space" aria-hidden="true" />
              </>
            )}
            </div>
          </div>

          <aside className="detail-side">
            <div className="detail-side-msgs" ref={threadRef}>
              {messages.map((message) =>
                message.role === 'user' ? (
                  <div key={message.id} className="side-row user">
                    <div className="side-bubble">{message.content}</div>
                  </div>
                ) : (
                  <div key={message.id} className="side-row coco">
                    <div className="who">
                      <span className="av">C</span>
                      Coco
                    </div>
                    <div>{message.content}</div>
                  </div>
                ),
              )}
            </div>
            {showSuggestions ? (
              <QuickSuggestions items={itinerary.quick_suggestions} onSelect={(text) => void pushTurn(text)} />
            ) : null}
            <form className="composer side-composer" onSubmit={handleSend}>
              <GlowComposerBox>
                <textarea
                  rows={1}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleComposerKey}
                  placeholder={revising ? 'Coco 正在改这份行程…' : '跟 Coco 说要改什么'}
                  aria-label="给 Coco 发修改"
                  disabled={revising}
                />
                <button
                  type="submit"
                  className="send-btn"
                  disabled={revising || draft.trim().length === 0}
                  aria-label="发送"
                >
                  ↑
                </button>
              </GlowComposerBox>
            </form>
          </aside>
        </>
      ) : null}
      <MicroDetailModal card={detailCard} onClose={() => setDetailCard(null)} />
    </div>
  )

  return <AppShell main={main} />
}

const DETAIL_STYLES = `
.ui-mark {
  display: inline-block;
  margin-right: 6px;
  font-style: normal;
  line-height: 1;
}
.detail-layout {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-main);
}
.detail-status {
  padding: 24px;
}
.detail-report {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.detail-report-head {
  flex-shrink: 0;
  z-index: 2;
  background: var(--bg-main);
  padding: 24px 24px 16px;
  border-bottom: 1px solid var(--border-subtle);
}
.detail-report-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 20px 28px 36px;
}
.detail-report-end-space {
  height: var(--report-end-space, 80vh);
  pointer-events: none;
}
.detail-title-row,
.detail-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.detail-title-row h1,
.day-section h2,
.report-section h2 {
  margin: 0;
  font-weight: 600;
}
.detail-title-row h1 {
  font-size: 20px;
  line-height: 1.3;
}
.detail-sub,
.report-note,
.micro-detail-body {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.4;
}
.detail-sub { margin: 8px 0 0; }
.report-section { margin-top: 24px; }
.report-section h2,
.day-section h2 {
  font-size: 16px;
  line-height: 1.3;
  margin-bottom: 8px;
}
.day-section { margin-top: 24px; }
.day-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  flex: 1;
}
.day-chip,
.suggest-chip {
  height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
}
.day-chip:hover,
.suggest-chip:hover { background: var(--bg-hover); }
.day-chip:active,
.suggest-chip:active { background: var(--bg-selected); }
.day-chip:focus-visible,
.suggest-chip:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.35);
  outline-offset: 2px;
  border-color: var(--border-strong);
}
.day-chip:disabled,
.suggest-chip:disabled { background: var(--bg-elevated); }
.day-chip.is-selected {
  background: var(--bg-selected);
  border-color: var(--border-strong);
}
.itinerary-glow {
  margin: 8px 0;
}
.itinerary-card {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: transparent;
  border: 0;
  border-radius: inherit;
}
.itinerary-card-main {
  flex: 1;
  text-align: left;
  background: transparent;
  border: 0;
  padding: 14px 16px;
  color: inherit;
}
.itinerary-card-main:hover { background: var(--bg-hover); }
.itinerary-card-main:active { background: var(--bg-selected); }
.itinerary-card-main:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.35);
  outline-offset: -2px;
}
.itinerary-card-main:disabled { background: transparent; }
.itinerary-card-main strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.itinerary-card-meta {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}
.itinerary-card-more { position: relative; padding: 8px 8px 0 0; }
.itinerary-card-menu {
  position: absolute;
  right: 8px;
  top: 40px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 8px 12px;
  z-index: 3;
}
.transit-leg {
  margin: 0 0 0 16px;
  padding: 8px 0 8px 12px;
  border-left: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.4;
}
.checklist {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.checklist label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}
.checklist input {
  accent-color: #ececec;
}
.map-panel {
  margin-top: 8px;
  min-height: 360px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.day-map {
  position: relative;
  min-height: 360px;
  flex: 1;
  background: #2a2a2a;
  border-radius: 14px;
  overflow: hidden;
}
.day-map-canvas {
  position: absolute;
  inset: 0;
}
.map-unconfigured {
  position: absolute;
  inset: 0;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  pointer-events: none;
}
.map-card-strip {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: 8px;
  overflow-x: auto;
}
.map-card-chip {
  height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-size: 13px;
  white-space: nowrap;
}
.map-card-chip:hover { background: var(--bg-hover); }
.map-card-chip:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.35);
  outline-offset: 2px;
}
.amap-day-label {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 8px;
  background: rgba(20, 20, 20, 0.82);
  color: #f5f5f5;
  font-size: 12px;
  line-height: 1.2;
}
.detail-side {
  width: 360px;
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: transparent;
  border-left: 1px solid var(--border-subtle);
}
.detail-side-msgs {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px;
}
.side-row { margin-bottom: 16px; }
.side-row.user { display: flex; justify-content: flex-end; }
.side-bubble {
  max-width: 72%;
  background: var(--bg-elevated);
  border-radius: 18px;
  padding: 10px 14px;
}
.side-row.coco .who {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}
.av {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bg-elevated);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}
.quick-suggestions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 0 16px 8px;
}
.suggest-chip {
  width: 100%;
  height: auto;
  min-height: 32px;
  padding: 8px 12px;
  white-space: normal;
  overflow: visible;
  text-align: left;
  line-height: 1.4;
}
.side-composer { padding: 12px 12px 20px; }
.micro-detail-body { margin: 0; font-size: 14px; }
@media (max-width: 1099px) {
  .detail-side { width: 300px; }
}
@media (max-width: 767px) {
  .detail-layout { flex-direction: column; }
  .detail-side { width: 100%; height: 42%; border-left: 0; border-top: 1px solid var(--border-subtle); }
}
@media (prefers-reduced-motion: reduce) {
  .detail-report-body { scroll-behavior: auto; }
}
`
