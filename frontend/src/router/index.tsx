import { useEffect } from 'react'
import { Route, Routes } from 'react-router'
import { AppShell } from '../components/layout/AppShell'
import { ItineraryDetailPage } from '../pages/ItineraryDetailPage'
import { TripListPage } from '../pages/TripListPage'
import { WorkbenchPage } from '../pages/WorkbenchPage'
import { useApp } from '../stores/AppProvider'

function TripListRoute() {
  const { setNav } = useApp()
  useEffect(() => {
    setNav('trips')
  }, [setNav])
  return <AppShell main={<TripListPage />} />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<WorkbenchPage />} />
      <Route path="/trips" element={<TripListRoute />} />
      <Route path="/itineraries/:id" element={<ItineraryDetailPage />} />
    </Routes>
  )
}
