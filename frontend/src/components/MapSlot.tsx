import { useEffect, useRef, useState } from 'react'
import { useApp } from '../stores/AppProvider'

const CHINA_CENTER: [number, number] = [104.2, 35.2]
const CHINA_ZOOM = 4
const CITY_ZOOM = 11

type AMapMap = { destroy?: () => void; setZoomAndCenter?: (zoom: number, center: [number, number]) => void }
type AMapCtor = {
  Map: new (
    container: string | HTMLElement,
    opts: { zoom: number; center: [number, number]; viewMode?: string },
  ) => AMapMap
}

declare global {
  interface Window {
    _AMapSecurityConfig?: { securityJsCode?: string }
    AMap?: AMapCtor
  }
}

function readMapHint(raw: unknown): [number, number] | null {
  if (!raw || typeof raw !== 'object') return null
  const hint = raw as { lng?: unknown; lat?: unknown }
  const lng = Number(hint.lng)
  const lat = Number(hint.lat)
  if (Number.isFinite(lng) && Number.isFinite(lat) && lng >= -180 && lng <= 180 && lat >= -90 && lat <= 90) {
    return [lng, lat]
  }
  return null
}

function loadAMapScript(key: string): Promise<AMapCtor> {
  if (window.AMap) return Promise.resolve(window.AMap)

  const existing = document.querySelector<HTMLScriptElement>('script[data-amap-jsapi="2.0"]')
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => {
        if (window.AMap) resolve(window.AMap)
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
      if (window.AMap) resolve(window.AMap)
      else reject(new Error('地图脚本未就绪'))
    }
    script.onerror = () => reject(new Error('地图脚本加载失败'))
    document.head.appendChild(script)
  })
}

export function MapSlot() {
  const { isMock, conversation } = useApp()
  const jsKey = import.meta.env.VITE_AMAP_JS_KEY?.trim() ?? ''
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE?.trim() ?? ''
  const jsKeyConfigured = Boolean(jsKey)
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<AMapMap | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'failed'>(
    jsKeyConfigured ? 'loading' : 'idle',
  )
  const hint = readMapHint(conversation?.map_hint)
  const centerLng = hint?.[0] ?? CHINA_CENTER[0]
  const centerLat = hint?.[1] ?? CHINA_CENTER[1]
  const zoom = hint ? CITY_ZOOM : CHINA_ZOOM

  useEffect(() => {
    if (!jsKeyConfigured) return

    if (!containerRef.current) return

    let cancelled = false
    if (securityCode) {
      window._AMapSecurityConfig = { securityJsCode: securityCode }
    }

    void loadAMapScript(jsKey)
      .then((AMap) => {
        if (cancelled || !containerRef.current) return
        mapRef.current = new AMap.Map(containerRef.current, {
          zoom,
          center: [centerLng, centerLat],
          viewMode: '2D',
        })
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('failed')
      })

    return () => {
      cancelled = true
      mapRef.current?.destroy?.()
      mapRef.current = null
    }
    // 首次挂载加载一次；视野变化由下面的 recenter effect 处理
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jsKey, jsKeyConfigured, securityCode])

  useEffect(() => {
    mapRef.current?.setZoomAndCenter?.(zoom, [centerLng, centerLat])
  }, [centerLat, centerLng, zoom])

  const copy =
    !jsKeyConfigured ? '🗺️ 地图未配置' : status === 'failed' ? '🗺️ 地图暂时无法显示' : status === 'ready' ? '' : '🗺️ 地图加载中'

  return (
    <div className="map-slot">
      <header className="panel-head">
        <h2>🗺️ 地图</h2>
        {isMock ? <span className="mock-badge">[Mock]</span> : null}
      </header>
      <div className="map-slot-frame" aria-label={jsKeyConfigured ? '地图槽' : '地图未配置'}>
        {jsKeyConfigured ? (
          <div
            ref={containerRef}
            style={{ position: 'absolute', inset: 0, borderRadius: 14, overflow: 'hidden' }}
          />
        ) : (
          <i className="map-pin" aria-hidden="true" />
        )}
        {copy ? <span className="map-slot-copy">{copy}</span> : null}
      </div>
    </div>
  )
}
