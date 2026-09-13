import { useEffect } from 'react'
import { BrowserRouter, useLocation } from 'react-router'
import { NewPlanModal } from './components/NewPlanModal'
import { AppRoutes } from './router/index'
import { AppProvider, useApp } from './stores/AppProvider'

function NavSync() {
  const { pathname } = useLocation()
  const { setNav, setMobileSidebarOpen, setMobileRightOpen } = useApp()

  useEffect(() => {
    if (pathname === '/trips' || pathname.startsWith('/itineraries/')) {
      setNav('trips')
    } else {
      setNav('chat')
    }
    setMobileSidebarOpen(false)
    setMobileRightOpen(false)
  }, [pathname, setNav, setMobileSidebarOpen, setMobileRightOpen])

  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <NavSync />
        <AppRoutes />
        <NewPlanModal />
      </AppProvider>
    </BrowserRouter>
  )
}
