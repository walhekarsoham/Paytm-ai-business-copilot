import type { ReactNode } from 'react'
import type { AppPage, MerchantSession } from '../../types/merchant'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

type DashboardLayoutProps = {
  children: ReactNode
  activePage: AppPage
  onNavigate: (page: AppPage) => void
  merchant: MerchantSession
  onLogout: () => void
}

export function DashboardLayout({ children, activePage, onNavigate, merchant, onLogout }: DashboardLayoutProps) {
  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} onNavigate={onNavigate} merchant={merchant} onLogout={onLogout} />
      <div className="main-panel">
        <Header pageTitle={activePage} merchant={merchant} onLogout={onLogout} />
        <main className="page-content">{children}</main>
      </div>
    </div>
  )
}
