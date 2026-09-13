import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link } from 'react-router'
import type { ConversationViewState } from '../../hooks/useConversation'
import type { ActivityLogEntry } from '../../mocks/planning'
import { useApp } from '../../stores/AppProvider'
import { ActivityLog } from '../ActivityLog'
import { GlowComposerBox } from '../ui/BorderGlow'
import { LogDetailModal } from '../LogDetailModal'
import { SpecialistStatus } from '../SpecialistStatus'
import { CocoTyping, MessageBubble } from './MessageBubble'

export const CHAT_CSS = `
.chat-thread-scroll { overflow: auto; }
.chat-inner { max-width: 760px; margin: 0 auto; }
.chat-row { margin: 0 0 20px; animation: chat-fade 160ms ease; }
.chat-row.is-user { display: flex; justify-content: flex-end; }
.user-bubble { background: var(--bg-elevated); border-radius: 18px; padding: 10px 14px; max-width: 72%; }
.coco-who { font-size: 13px; font-weight: 500; line-height: 1.3; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.coco-av { width: 22px; height: 22px; border-radius: 50%; background: var(--bg-elevated); display: grid; place-items: center; font-size: 11px; font-weight: 600; }
.coco-text { color: var(--text-primary); }
.coco-text.is-fail { border-left: 2px solid #fff; padding-left: 12px; }
.coco-dots { display: flex; gap: 6px; padding: 8px 0; }
.coco-dots i { width: 6px; height: 6px; border-radius: 50%; background: #fff; opacity: 0.35; animation: coco-dot 1s ease infinite; }
.coco-dots i:nth-child(2) { animation-delay: 0.2s; }
.coco-dots i:nth-child(3) { animation-delay: 0.4s; }
.spec-list { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 13px; line-height: 1.4; color: var(--text-secondary); }
.spec-row { display: flex; align-items: center; gap: 8px; }
.spec-row.is-not_started { color: var(--text-muted); }
.spec-row.is-running { color: var(--text-primary); }
.spec-spin { width: 10px; height: 10px; border: 1.5px solid var(--text-muted); border-top-color: #fff; border-radius: 50%; animation: spec-spin 1s linear infinite; flex-shrink: 0; }
.activity-log { margin-top: 14px; font-size: 13px; line-height: 1.4; color: var(--text-secondary); }
.activity-log-head { display: flex; align-items: center; gap: 6px; background: none; border: 0; padding: 0; color: var(--text-primary); font: inherit; font-weight: 500; text-align: left; }
.activity-log-head:hover { color: #fff; }
.activity-log-head:active { color: var(--text-secondary); }
.activity-log-head:focus-visible { outline: 2px solid rgba(255,255,255,0.35); outline-offset: 2px; }
.activity-log-head:disabled { color: var(--text-muted); }
.activity-chev { width: 10px; color: var(--text-muted); }
.activity-log-body { margin: 10px 0 0 16px; display: flex; flex-direction: column; gap: 7px; }
.activity-step { background: none; border: 0; padding: 2px 4px; margin-left: -4px; text-align: left; color: var(--text-secondary); font: inherit; border-radius: 6px; cursor: default; }
.activity-step.is-clickable { cursor: pointer; }
.activity-step:hover { color: var(--text-primary); background: var(--bg-hover); }
.activity-step:active { color: var(--text-primary); background: var(--bg-selected); }
.activity-step:focus-visible { outline: 2px solid rgba(255,255,255,0.35); outline-offset: 2px; }
.activity-step:disabled { color: var(--text-secondary); background: transparent; cursor: default; }
.view-trip { margin-top: 12px; display: inline-flex; align-items: center; text-decoration: none; }
.log-detail-body { white-space: pre-wrap; color: var(--text-secondary); font: 400 14px/1.5 var(--font-ui); max-height: 60vh; overflow: auto; margin: 0; }
.map-slot { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.map-slot-frame { flex: 1; min-height: 0; margin: 16px; border-radius: 14px; background: linear-gradient(var(--border-subtle), var(--border-subtle)) center/1px 100% no-repeat, linear-gradient(var(--border-subtle), var(--border-subtle)) center/100% 1px no-repeat, #2a2a2a; position: relative; }
.map-slot-copy { position: absolute; left: 50%; top: 46%; transform: translate(-50%,-50%); color: var(--text-muted); font-size: 13px; text-align: center; }
.map-pin { width: 10px; height: 10px; background: #fff; border-radius: 50%; position: absolute; left: 52%; top: 48%; }
@keyframes chat-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes coco-dot { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }
@keyframes spec-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .chat-row, .coco-dots i, .spec-spin { animation: none; }
}
`

export function ChatThread({ chat }: { chat: ConversationViewState }) {
  const { conversation, isMock } = useApp()
  const [draft, setDraft] = useState('')
  const [detail, setDetail] = useState<ActivityLogEntry | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const empty = draft.trim().length === 0
  const lastAssistantId = [...chat.messages].reverse().find((item) => item.role === 'assistant')?.id ?? null
  const showWelcome = chat.messages.length === 0 && !chat.waitingCoco

  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [chat.messages, chat.activityLog, chat.waitingCoco])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (empty || chat.sending) return
    const text = draft
    setDraft('')
    void chat.send(text)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!empty && !chat.sending) {
        const text = draft
        setDraft('')
        void chat.send(text)
      }
    }
  }

  return (
    <div className="chat-col">
      <style>{CHAT_CSS}</style>
      <div className="chat-scroll chat-thread-scroll" ref={scrollRef}>
        {showWelcome ? (
          <div className="welcome">
            <span className="welcome-mark" aria-hidden="true">
              ✈️
            </span>
            <strong>和 Coco 规划一趟旅行</strong>
            <span>
              {conversation
                ? '🗺️ 想去哪，直接跟 Coco 说。已按表单进入对话，不会立刻出方案。'
                : '🗺️ 想去哪，直接跟 Coco 说。'}
            </span>
            {isMock ? <span className="mock-badge welcome-mock">[Mock]</span> : null}
          </div>
        ) : (
          <div className="chat-inner">
            {isMock ? <span className="mock-badge">[Mock]</span> : null}
            {chat.messages.map((message) => {
              const isLastAssistant = message.id === lastAssistantId
              const failed = chat.planning.status === 'failed' && isLastAssistant && message.role === 'assistant'
              const showSpecs =
                message.role === 'assistant' &&
                (message.id === chat.logHostId || (chat.planning.status === 'idle' && isLastAssistant))
              const showLog =
                message.role === 'assistant' &&
                message.id === chat.logHostId &&
                (chat.activityLog.length > 0 || chat.planning.status === 'running')
              const showTrip =
                message.role === 'assistant' &&
                isLastAssistant &&
                chat.planning.status === 'succeeded' &&
                Boolean(chat.planning.itinerary_id)

              return (
                <MessageBubble key={message.id} message={message} failed={failed}>
                  {showSpecs ? <SpecialistStatus specialists={chat.planning.specialists} /> : null}
                  {showLog ? (
                    <ActivityLog
                      entries={chat.activityLog}
                      running={chat.planning.status === 'running'}
                      onStepClick={setDetail}
                    />
                  ) : null}
                  {showTrip && chat.planning.itinerary_id ? (
                    <Link className="cta-btn view-trip" to={`/itineraries/${chat.planning.itinerary_id}`}>
                      👀 查看行程
                    </Link>
                  ) : null}
                </MessageBubble>
              )
            })}
            {chat.waitingCoco ? <CocoTyping /> : null}
            {chat.sendError ? <p className="field-hint">{chat.sendError}</p> : null}
          </div>
        )}
      </div>
      <form className="composer" onSubmit={handleSubmit}>
        <GlowComposerBox>
          <textarea
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="从上海出发去杭州，轻松 5 天…"
            aria-label="给 Coco 发消息"
          />
          <button type="submit" className="send-btn" disabled={empty || chat.sending} aria-label="发送">
            ↑
          </button>
        </GlowComposerBox>
      </form>
      <LogDetailModal entry={detail} onClose={() => setDetail(null)} />
    </div>
  )
}
