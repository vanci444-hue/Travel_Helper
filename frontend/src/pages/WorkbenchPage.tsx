import { ChatThread } from '../components/chat/ChatThread'
import { InspirationPanel } from '../components/InspirationPanel'
import { MapSlot } from '../components/MapSlot'
import { AppShell } from '../components/layout/AppShell'
import { useConversation } from '../hooks/useConversation'

export function WorkbenchPage() {
  const chat = useConversation()
  const rightLabel = chat.hasStarted ? '地图' : '灵感'

  return (
    <AppShell
      main={<ChatThread chat={chat} />}
      right={chat.hasStarted ? <MapSlot /> : <InspirationPanel />}
      rightLabel={rightLabel}
    />
  )
}
