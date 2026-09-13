import { useEffect, type FormEvent } from 'react'
import { useApp } from '../stores/AppProvider'
import type { Pace } from '../types/conversation'
import { PACE_MARK } from '../ui/travelMarks'

const PACE_OPTIONS: { value: Pace; label: string }[] = [
  { value: 'relaxed', label: `${PACE_MARK.relaxed} 轻松` },
  { value: 'moderate', label: `${PACE_MARK.moderate} 适中` },
  { value: 'packed', label: `${PACE_MARK.packed} 紧凑` },
]

export function NewPlanModal() {
  const {
    newPlanOpen,
    closeNewPlan,
    draft,
    setDraft,
    submitNewPlan,
    creating,
    createError,
  } = useApp()

  useEffect(() => {
    if (!newPlanOpen) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') closeNewPlan()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [newPlanOpen, closeNewPlan])

  if (!newPlanOpen) return null

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    await submitNewPlan()
  }

  return (
    <div
      className="overlay"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) closeNewPlan()
      }}
    >
      <div className="modal" role="dialog" aria-labelledby="new-plan-title" aria-modal="true">
        <h2 id="new-plan-title">✈️ 新建计划</h2>
        <form onSubmit={handleSubmit}>
          <label htmlFor="plan-where">📍 去哪</label>
          <input
            id="plan-where"
            value={draft.destination_text}
            onChange={(event) => setDraft({ destination_text: event.target.value })}
            placeholder="例如杭州"
          />
          <label htmlFor="plan-when">📅 何时</label>
          <input
            id="plan-when"
            value={draft.when_text}
            onChange={(event) => setDraft({ when_text: event.target.value })}
            placeholder="例如 5 天"
          />
          <label htmlFor="plan-adults">👥 和谁 · 成人</label>
          <input
            id="plan-adults"
            value={draft.adults_text}
            onChange={(event) => setDraft({ adults_text: event.target.value })}
            placeholder="例如 2"
          />
          <label htmlFor="plan-children">🧒 和谁 · 儿童</label>
          <input
            id="plan-children"
            value={draft.children_text}
            onChange={(event) => setDraft({ children_text: event.target.value })}
            placeholder="例如 0"
          />
          <label htmlFor="plan-budget">💰 预算</label>
          <input
            id="plan-budget"
            value={draft.budget_text}
            onChange={(event) => setDraft({ budget_text: event.target.value })}
            placeholder="例如 20000"
          />
          <span className="field-label">🚶 节奏</span>
          <div className="pace-row" role="group" aria-label="节奏">
            {PACE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`pace-chip${draft.pace === option.value ? ' is-selected' : ''}`}
                onClick={() =>
                  setDraft({ pace: draft.pace === option.value ? null : option.value })
                }
              >
                {option.label}
              </button>
            ))}
          </div>
          <label htmlFor="plan-wish">📝 目前已知的计划</label>
          <textarea
            id="plan-wish"
            rows={2}
            value={draft.wish_text}
            onChange={(event) => setDraft({ wish_text: event.target.value })}
            placeholder="可选"
          />
          {createError ? <p className="field-hint">{createError}</p> : null}
          <div className="modal-actions">
            <button type="button" className="ghost-btn" onClick={closeNewPlan}>
              取消
            </button>
            <button type="submit" className="cta-btn" disabled={creating}>
              开始聊
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
