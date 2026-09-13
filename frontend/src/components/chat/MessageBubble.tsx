import type { ReactNode } from 'react'
import type { MessagePublic } from '../../types/conversation'

export function MessageBubble({
  message,
  failed = false,
  children,
}: {
  message: MessagePublic
  failed?: boolean
  children?: ReactNode
}) {
  if (message.role === 'user') {
    return (
      <div className="chat-row is-user">
        <div className="user-bubble">{message.content}</div>
      </div>
    )
  }

  return (
    <div className="chat-row is-coco">
      <div className="coco-who">
        <span className="coco-av" aria-hidden="true">
          C
        </span>
        <span className="coco-name">Coco</span>
      </div>
      <div className={failed ? 'coco-text is-fail' : 'coco-text'}>{message.content}</div>
      {children}
    </div>
  )
}

export function CocoTyping() {
  return (
    <div className="chat-row is-coco" aria-live="polite" aria-label="Coco 正在回复">
      <div className="coco-who">
        <span className="coco-av" aria-hidden="true">
          C
        </span>
        <span className="coco-name">Coco</span>
      </div>
      <div className="coco-dots">
        <i />
        <i />
        <i />
      </div>
    </div>
  )
}
