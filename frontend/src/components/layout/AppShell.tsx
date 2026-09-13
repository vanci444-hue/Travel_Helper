import { useEffect, useState, type ReactNode } from 'react'
import { RIGHT_COL_MAX, RIGHT_COL_MIN, useRightColWidth } from '../../hooks/useRightColWidth'
import { useApp } from '../../stores/AppProvider'
import { Galaxy } from '../ui/Galaxy'
import { Sidebar } from './Sidebar'

export function AppShell({
  main,
  right,
  rightLabel = '灵感',
}: {
  main: ReactNode
  right?: ReactNode
  rightLabel?: string
}) {
  const { mobileSidebarOpen, setMobileSidebarOpen, mobileRightOpen, setMobileRightOpen } = useApp()
  const showRight = Boolean(right)
  const rightCol = useRightColWidth()
  const [desktopRight, setDesktopRight] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(min-width: 1100px)').matches,
  )

  useEffect(() => {
    const media = window.matchMedia('(min-width: 1100px)')
    const sync = () => {
      setDesktopRight(media.matches)
      if (media.matches) setMobileRightOpen(false)
    }
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [setMobileRightOpen])

  function openSidebar() {
    setMobileRightOpen(false)
    setMobileSidebarOpen(true)
  }

  function openRight() {
    setMobileSidebarOpen(false)
    setMobileRightOpen(true)
  }

  return (
    <div
      className={`app-shell${rightCol.dragging ? ' is-resizing-right' : ''}${showRight ? ' has-right-toggle' : ''}`}
    >
      <div className="galaxy-layer" aria-hidden="true">
        <Galaxy
          mouseRepulsion
          mouseInteraction
          density={2.5}
          glowIntensity={0.3}
          saturation={0}
          hueShift={140}
          twinkleIntensity={0.3}
          rotationSpeed={0.1}
          repulsionStrength={2}
          autoCenterRepulsion={0}
          starSpeed={0.5}
          speed={1}
        />
      </div>
      <button type="button" className="icon-btn mobile-only sidebar-toggle" onClick={openSidebar} aria-label="打开菜单">
        ☰
      </button>
      {showRight ? (
        <button type="button" className="ghost-btn mobile-right-toggle" onClick={openRight}>
          {rightLabel}
        </button>
      ) : null}
      {mobileSidebarOpen ? (
        <button
          type="button"
          className="drawer-mask sidebar-drawer-mask"
          aria-label="关闭菜单"
          onClick={() => setMobileSidebarOpen(false)}
        />
      ) : null}
      {showRight && mobileRightOpen ? (
        <button
          type="button"
          className="drawer-mask right-drawer-mask"
          aria-label={`关闭${rightLabel}`}
          onClick={() => setMobileRightOpen(false)}
        />
      ) : null}
      <div className={`sidebar-slot${mobileSidebarOpen ? ' is-open' : ''}`}>
        <Sidebar />
      </div>
      <main className="main-col">{main}</main>
      {showRight ? (
        <aside
          className={`right-col${mobileRightOpen ? ' is-open' : ''}`}
          style={desktopRight ? { width: rightCol.width } : undefined}
        >
          <button
            type="button"
            className={`right-col-resizer${rightCol.dragging ? ' is-dragging' : ''}`}
            aria-label="调整地图列宽度"
            aria-orientation="vertical"
            aria-valuemin={RIGHT_COL_MIN}
            aria-valuemax={RIGHT_COL_MAX}
            aria-valuenow={rightCol.width}
            aria-valuetext={`${rightCol.width} 像素`}
            onPointerDown={rightCol.onPointerDown}
            onKeyDown={rightCol.onKeyDown}
            onDoubleClick={rightCol.onDoubleClick}
          />
          <button
            type="button"
            className="icon-btn mobile-right-close"
            onClick={() => setMobileRightOpen(false)}
            aria-label={`关闭${rightLabel}`}
          >
            ×
          </button>
          {right}
        </aside>
      ) : null}
    </div>
  )
}
