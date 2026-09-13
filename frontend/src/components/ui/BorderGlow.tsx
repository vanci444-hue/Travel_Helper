import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FocusEvent,
  type PointerEvent,
  type ReactNode,
} from 'react'

export const BORDER_GLOW_COLORS = ['#c084fc', '#f472b6', '#38bdf8'] as const

export interface BorderGlowProps {
  children: ReactNode
  className?: string
  edgeSensitivity?: number
  glowColor?: string
  backgroundColor?: string
  borderRadius?: number
  glowRadius?: number
  glowIntensity?: number
  coneSpread?: number
  animated?: boolean
  spinning?: boolean
  spinDegreesPerSecond?: number
  colors?: string[]
  fillOpacity?: number
}

function parseHSL(hslStr: string) {
  const match = hslStr.match(/([\d.]+)\s*([\d.]+)%?\s*([\d.]+)%?/)
  if (!match) return { h: 40, s: 80, l: 80 }
  return { h: parseFloat(match[1]), s: parseFloat(match[2]), l: parseFloat(match[3]) }
}

function buildBoxShadow(glowColor: string, intensity: number) {
  const { h, s, l } = parseHSL(glowColor)
  const base = `${h}deg ${s}% ${l}%`
  const layers: Array<[number, number, number, number, number, boolean]> = [
    [0, 0, 0, 1, 100, true],
    [0, 0, 1, 0, 60, true],
    [0, 0, 3, 0, 50, true],
    [0, 0, 6, 0, 40, true],
    [0, 0, 15, 0, 30, true],
    [0, 0, 25, 2, 20, true],
    [0, 0, 50, 2, 10, true],
    [0, 0, 1, 0, 60, false],
    [0, 0, 3, 0, 50, false],
    [0, 0, 6, 0, 40, false],
    [0, 0, 15, 0, 30, false],
    [0, 0, 25, 2, 20, false],
    [0, 0, 50, 2, 10, false],
  ]
  return layers
    .map(([x, y, blur, spread, alpha, inset]) => {
      const a = Math.min(alpha * intensity, 100)
      return `${inset ? 'inset ' : ''}${x}px ${y}px ${blur}px ${spread}px hsl(${base} / ${a}%)`
    })
    .join(', ')
}

function easeOutCubic(x: number) {
  return 1 - Math.pow(1 - x, 3)
}

function easeInCubic(x: number) {
  return x * x * x
}

function animateValue({
  start = 0,
  end = 100,
  duration = 1000,
  delay = 0,
  ease = easeOutCubic,
  onUpdate,
  onEnd,
  isCancelled,
}: {
  start?: number
  end?: number
  duration?: number
  delay?: number
  ease?: (x: number) => number
  onUpdate: (value: number) => void
  onEnd?: () => void
  isCancelled: () => boolean
}) {
  const t0 = performance.now() + delay
  function tick() {
    if (isCancelled()) return
    const elapsed = performance.now() - t0
    const t = Math.min(elapsed / duration, 1)
    onUpdate(start + (end - start) * ease(t))
    if (t < 1) requestAnimationFrame(tick)
    else if (onEnd) onEnd()
  }
  window.setTimeout(() => requestAnimationFrame(tick), delay)
}

const GRADIENT_POSITIONS = ['80% 55%', '69% 34%', '8% 6%', '41% 38%', '86% 85%', '82% 18%', '51% 4%']
const COLOR_MAP = [0, 1, 2, 0, 1, 2, 1]

function buildMeshGradients(colors: string[]) {
  const gradients: string[] = []
  for (let i = 0; i < 7; i += 1) {
    const c = colors[Math.min(COLOR_MAP[i], colors.length - 1)]
    gradients.push(`radial-gradient(at ${GRADIENT_POSITIONS[i]}, ${c} 0px, transparent 50%)`)
  }
  gradients.push(`linear-gradient(${colors[0]} 0 100%)`)
  return gradients
}

function isLightColor(color: string) {
  const value = color.trim().replace('#', '')
  if (!/^[\da-f]{3}([\da-f]{3})?$/i.test(value)) return false
  const hex = value.length === 3 ? value.split('').map((char) => char + char).join('') : value
  const red = Number.parseInt(hex.slice(0, 2), 16)
  const green = Number.parseInt(hex.slice(2, 4), 16)
  const blue = Number.parseInt(hex.slice(4, 6), 16)
  return red * 0.2126 + green * 0.7152 + blue * 0.0722 > 180
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function BorderGlow({
  children,
  className = '',
  edgeSensitivity = 30,
  glowColor = '40 80 80',
  backgroundColor = '#2f2f2f',
  borderRadius = 14,
  glowRadius = 24,
  glowIntensity = 1,
  coneSpread = 25,
  animated = false,
  spinning = false,
  spinDegreesPerSecond = 60,
  colors = [...BORDER_GLOW_COLORS],
  fillOpacity = 0.5,
}: BorderGlowProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [isHovered, setIsHovered] = useState(false)
  const [cursorAngle, setCursorAngle] = useState(45)
  const [edgeProximity, setEdgeProximity] = useState(0)
  const [sweepActive, setSweepActive] = useState(false)
  const [reduceMotion, setReduceMotion] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setReduceMotion(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  const getCenterOfElement = useCallback((el: HTMLElement) => {
    const { width, height } = el.getBoundingClientRect()
    return [width / 2, height / 2] as const
  }, [])

  const getEdgeProximity = useCallback(
    (el: HTMLElement, x: number, y: number) => {
      const [cx, cy] = getCenterOfElement(el)
      const dx = x - cx
      const dy = y - cy
      let kx = Infinity
      let ky = Infinity
      if (dx !== 0) kx = cx / Math.abs(dx)
      if (dy !== 0) ky = cy / Math.abs(dy)
      return Math.min(Math.max(1 / Math.min(kx, ky), 0), 1)
    },
    [getCenterOfElement],
  )

  const getCursorAngle = useCallback(
    (el: HTMLElement, x: number, y: number) => {
      const [cx, cy] = getCenterOfElement(el)
      const dx = x - cx
      const dy = y - cy
      if (dx === 0 && dy === 0) return 0
      const radians = Math.atan2(dy, dx)
      let degrees = (radians * 180) / Math.PI + 90
      if (degrees < 0) degrees += 360
      return degrees
    },
    [getCenterOfElement],
  )

  const handlePointerMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (reduceMotion || spinning) return
      const card = cardRef.current
      if (!card) return
      const rect = card.getBoundingClientRect()
      const x = event.clientX - rect.left
      const y = event.clientY - rect.top
      setEdgeProximity(getEdgeProximity(card, x, y))
      setCursorAngle(getCursorAngle(card, x, y))
    },
    [getCursorAngle, getEdgeProximity, reduceMotion, spinning],
  )

  useEffect(() => {
    if (!spinning || reduceMotion) return
    let cancelled = false
    let last = performance.now()
    let angle = 45
    setEdgeProximity(0.88)
    function tick(now: number) {
      if (cancelled) return
      const delta = now - last
      last = now
      angle = (angle + (delta / 1000) * spinDegreesPerSecond) % 360
      setCursorAngle(angle)
      requestAnimationFrame(tick)
    }
    const frame = requestAnimationFrame(tick)
    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [reduceMotion, spinDegreesPerSecond, spinning])

  useEffect(() => {
    if (!animated || prefersReducedMotion()) return
    let cancelled = false
    const isCancelled = () => cancelled
    const angleStart = 110
    const angleEnd = 465
    setSweepActive(true)
    setCursorAngle(angleStart)

    animateValue({
      duration: 500,
      onUpdate: (v) => {
        if (!cancelled) setEdgeProximity(v / 100)
      },
      isCancelled,
    })
    animateValue({
      ease: easeInCubic,
      duration: 1500,
      end: 50,
      onUpdate: (v) => {
        if (!cancelled) setCursorAngle((angleEnd - angleStart) * (v / 100) + angleStart)
      },
      isCancelled,
    })
    animateValue({
      ease: easeOutCubic,
      delay: 1500,
      duration: 2250,
      start: 50,
      end: 100,
      onUpdate: (v) => {
        if (!cancelled) setCursorAngle((angleEnd - angleStart) * (v / 100) + angleStart)
      },
      isCancelled,
    })
    animateValue({
      ease: easeInCubic,
      delay: 2500,
      duration: 1500,
      start: 100,
      end: 0,
      onUpdate: (v) => {
        if (!cancelled) setEdgeProximity(v / 100)
      },
      onEnd: () => {
        if (!cancelled) setSweepActive(false)
      },
      isCancelled,
    })

    return () => {
      cancelled = true
    }
  }, [animated])

  const colorSensitivity = edgeSensitivity + 20
  const isVisible = !reduceMotion && (isHovered || sweepActive || spinning)
  const borderOpacity = isVisible
    ? Math.max(0, (edgeProximity * 100 - colorSensitivity) / (100 - colorSensitivity))
    : 0
  const glowOpacity = isVisible
    ? Math.max(0, (edgeProximity * 100 - edgeSensitivity) / (100 - edgeSensitivity))
    : 0

  const meshGradients = buildMeshGradients(colors)
  const borderBg = meshGradients.map((g) => `${g} border-box`)
  const fillBg = meshGradients.map((g) => `${g} padding-box`)
  const angleDeg = `${cursorAngle.toFixed(3)}deg`
  const lightSurface = isLightColor(backgroundColor)

  return (
    <div
      ref={cardRef}
      onPointerMove={handlePointerMove}
      onPointerEnter={() => {
        if (!reduceMotion) setIsHovered(true)
      }}
      onPointerLeave={() => setIsHovered(false)}
      className={['border-glow', className].filter(Boolean).join(' ')}
      style={{
        background: backgroundColor,
        borderColor: lightSurface ? 'rgb(24 24 27 / 12%)' : 'rgb(255 255 255 / 15%)',
        borderRadius: `${borderRadius}px`,
        boxShadow: lightSurface
          ? 'rgb(24 24 27 / 4%) 0 1px 2px, rgb(24 24 27 / 5%) 0 8px 24px'
          : 'rgba(0,0,0,0.1) 0 1px 2px, rgba(0,0,0,0.1) 0 2px 4px, rgba(0,0,0,0.1) 0 4px 8px, rgba(0,0,0,0.1) 0 8px 16px, rgba(0,0,0,0.1) 0 16px 32px, rgba(0,0,0,0.1) 0 32px 64px',
      }}
    >
      <div
        className="border-glow-layer"
        style={{
          border: '1px solid transparent',
          background: [
            `linear-gradient(${backgroundColor} 0 100%) padding-box`,
            'linear-gradient(rgb(255 255 255 / 0%) 0% 100%) border-box',
            ...borderBg,
          ].join(', '),
          opacity: borderOpacity,
          maskImage: `conic-gradient(from ${angleDeg} at center, black ${coneSpread}%, transparent ${coneSpread + 15}%, transparent ${100 - coneSpread - 15}%, black ${100 - coneSpread}%)`,
          WebkitMaskImage: `conic-gradient(from ${angleDeg} at center, black ${coneSpread}%, transparent ${coneSpread + 15}%, transparent ${100 - coneSpread - 15}%, black ${100 - coneSpread}%)`,
          transition: isVisible ? 'opacity 0.25s ease-out' : 'opacity 0.75s ease-in-out',
        }}
      />
      <div
        className="border-glow-layer"
        style={{
          border: '1px solid transparent',
          background: fillBg.join(', '),
          maskImage: [
            'linear-gradient(to bottom, black, black)',
            'radial-gradient(ellipse at 50% 50%, black 40%, transparent 65%)',
            'radial-gradient(ellipse at 66% 66%, black 5%, transparent 40%)',
            'radial-gradient(ellipse at 33% 33%, black 5%, transparent 40%)',
            'radial-gradient(ellipse at 66% 33%, black 5%, transparent 40%)',
            'radial-gradient(ellipse at 33% 66%, black 5%, transparent 40%)',
            `conic-gradient(from ${angleDeg} at center, transparent 5%, black 15%, black 85%, transparent 95%)`,
          ].join(', '),
          WebkitMaskImage: [
            'linear-gradient(to bottom, black, black)',
            'radial-gradient(ellipse at 50% 50%, black 40%, transparent 65%)',
            'radial-gradient(ellipse at 66% 66%, black 5%, transparent 40%)',
            'radial-gradient(ellipse at 33% 33%, black 5%, transparent 40%)',
            'radial-gradient(ellipse at 66% 33%, black 5%, transparent 40%)',
            'radial-gradient(ellipse at 33% 66%, black 5%, transparent 40%)',
            `conic-gradient(from ${angleDeg} at center, transparent 5%, black 15%, black 85%, transparent 95%)`,
          ].join(', '),
          maskComposite: 'subtract, add, add, add, add, add',
          WebkitMaskComposite: 'source-out, source-over, source-over, source-over, source-over, source-over',
          opacity: borderOpacity * fillOpacity,
          mixBlendMode: lightSurface ? 'normal' : 'soft-light',
          transition: isVisible ? 'opacity 0.25s ease-out' : 'opacity 0.75s ease-in-out',
        }}
      />
      <span
        className="border-glow-outer"
        style={{
          inset: `${-glowRadius}px`,
          maskImage: `conic-gradient(from ${angleDeg} at center, black 2.5%, transparent 10%, transparent 90%, black 97.5%)`,
          WebkitMaskImage: `conic-gradient(from ${angleDeg} at center, black 2.5%, transparent 10%, transparent 90%, black 97.5%)`,
          opacity: glowOpacity,
          mixBlendMode: lightSurface ? 'normal' : 'plus-lighter',
          transition: isVisible ? 'opacity 0.25s ease-out' : 'opacity 0.75s ease-in-out',
        }}
      >
        <span
          className="border-glow-outer-inner"
          style={{
            inset: `${glowRadius}px`,
            boxShadow: buildBoxShadow(glowColor, glowIntensity),
          }}
        />
      </span>
      <div className="border-glow-content">{children}</div>
    </div>
  )
}

export function GlowComposerBox({ children }: { children: ReactNode }) {
  const [focused, setFocused] = useState(false)

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    const next = event.relatedTarget
    if (next instanceof Node && event.currentTarget.contains(next)) return
    setFocused(false)
  }

  return (
    <div className="composer-glow-host" onFocus={() => setFocused(true)} onBlur={handleBlur}>
      <BorderGlow
        className="composer-glow"
        backgroundColor="#2f2f2f"
        borderRadius={14}
        glowRadius={22}
        glowColor="40 80 80"
        colors={[...BORDER_GLOW_COLORS]}
        spinning={focused}
      >
        <div className="composer-box">{children}</div>
      </BorderGlow>
    </div>
  )
}
