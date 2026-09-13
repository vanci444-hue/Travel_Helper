import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { GlowComposerBox } from './ui/BorderGlow'

export function Composer() {
  const [text, setText] = useState('')
  const empty = text.trim().length === 0

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    // T-001 只保证可输入与空发送禁用；发出后对话/地图由 T-002 承接。
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <GlowComposerBox>
        <textarea
          rows={1}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="从上海出发去杭州，轻松 5 天…"
          aria-label="给 Coco 发消息"
        />
        <button type="submit" className="send-btn" disabled={empty} aria-label="发送">
          ↑
        </button>
      </GlowComposerBox>
    </form>
  )
}
