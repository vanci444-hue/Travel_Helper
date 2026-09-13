import { useLocation, useNavigate } from 'react-router'
import logoMark from '../../assets/xtrip-logo.png'
import { useApp } from '../../stores/AppProvider'

function IconChat() {
  return (
    <svg className="nav-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M4 5.5A1.5 1.5 0 0 1 5.5 4h9A1.5 1.5 0 0 1 16 5.5v6A1.5 1.5 0 0 1 14.5 13H8l-3.2 2.4A.5.5 0 0 1 4 15V5.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
      />
    </svg>
  )
}

function IconTrips() {
  return (
    <svg className="nav-icon" viewBox="0 0 20 20" aria-hidden="true">
      <rect x="3.5" y="4.5" width="13" height="11" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M6 8h8M6 11h5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

function IconPlus() {
  return (
    <svg className="nav-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M10 4.5v11M4.5 10h11" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

export function Sidebar() {
  const {
    setNav,
    openNewPlan,
    sidebarCollapsed,
    toggleSidebarCollapsed,
    setMobileSidebarOpen,
    isMock,
  } = useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const onChat = location.pathname === '/'
  const onTripsSection =
    location.pathname === '/trips' || location.pathname.startsWith('/itineraries/')

  return (
    <aside className={`sidebar${sidebarCollapsed ? ' is-collapsed' : ''}`}>
      <div className="brand-row">
        <button
          type="button"
          className="brand"
          onClick={() => {
            setNav('chat')
            setMobileSidebarOpen(false)
            if (location.pathname !== '/') navigate('/')
          }}
        >
          <img className="brand-mark" src={logoMark} alt="" />
          <span className="brand-name">Xtrip</span>
        </button>
        <button
          type="button"
          className="icon-btn collapse-btn"
          onClick={toggleSidebarCollapsed}
          aria-label={sidebarCollapsed ? '展开侧栏' : '折叠侧栏'}
        >
          {sidebarCollapsed ? '›' : '‹'}
        </button>
      </div>
      <nav className="side-nav" aria-label="主导航">
        <button
          type="button"
          className={`nav-item${onChat ? ' is-selected' : ''}`}
          onClick={() => {
            setNav('chat')
            setMobileSidebarOpen(false)
            if (location.pathname !== '/') navigate('/')
          }}
        >
          <IconChat />
          <span>对话</span>
        </button>
        <button
          type="button"
          className={`nav-item${onTripsSection ? ' is-selected' : ''}`}
          onClick={() => {
            setNav('trips')
            setMobileSidebarOpen(false)
            if (location.pathname !== '/trips') navigate('/trips')
          }}
        >
          <IconTrips />
          <span>行程</span>
        </button>
        <button
          type="button"
          className="nav-item"
          onClick={() => {
            if (location.pathname !== '/') navigate('/')
            openNewPlan()
          }}
        >
          <IconPlus />
          <span>新建计划</span>
        </button>
      </nav>
      <div className="side-foot">
        <span>Demo · 无登录</span>
        {isMock ? <span className="mock-badge">[Mock]</span> : null}
      </div>
    </aside>
  )
}
