import {
  Boxes,
  CircleHelp,
  CircleDollarSign,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Megaphone,
  PackageSearch,
  Settings2,
  Sparkles,
} from 'lucide-react'
import type { AppPage, MerchantSession } from '../../types/merchant'

const navigation: { label: AppPage; icon: typeof LayoutDashboard; isNew?: boolean }[] = [
  { label: 'Overview', icon: LayoutDashboard },
  { label: 'Sales', icon: CircleDollarSign },
  { label: 'Products', icon: PackageSearch },
  { label: 'Inventory', icon: Boxes },
  { label: 'AI Copilot', icon: Sparkles, isNew: true },
  { label: 'Campaigns', icon: Megaphone },
  { label: 'Settings', icon: Settings2 },
]

type SidebarProps = {
  activePage: AppPage
  onNavigate: (page: AppPage) => void
  merchant: MerchantSession
  onLogout: () => void
}

export function Sidebar({ activePage, onNavigate, merchant, onLogout }: SidebarProps) {
  return (
    <aside className="sidebar">
      <a className="brand" href="#overview" aria-label="Paytm for Business home" onClick={(event) => { event.preventDefault(); onNavigate('Overview') }}>
        <img className="brand-logo" src="/paytm-business-logo.svg" alt="Paytm for Business" />
      </a>

      <div className="workspace-label">WORKSPACE</div>
      <button className="store-switcher" type="button">
        <span className="store-avatar">{merchant.businessName[0]?.toUpperCase() ?? 'G'}</span>
        <span className="store-details"><strong>{merchant.businessName}</strong><small>Grocery merchant</small></span>
        <span className="switcher-chevron">⌄</span>
      </button>

      <nav className="primary-nav" aria-label="Main navigation">
        {navigation.map(({ label, icon: Icon, isNew }) => (
          <button key={label} type="button" title={label} aria-label={label} aria-current={activePage === label ? 'page' : undefined} onClick={() => onNavigate(label)} className={`nav-link${activePage === label ? ' active' : ''}`}>
            <Icon size={18} strokeWidth={1.8} />
            <span>{label}</span>
            {isNew && <span className="new-pill">NEW</span>}
          </button>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <a href="#help" className="nav-link"><LifeBuoy size={18} /><span>Help & support</span></a>
        <button className="nav-link sidebar-logout" type="button" onClick={onLogout}><LogOut size={18} /><span>Sign out</span></button>
        <div className="sidebar-footer"><CircleHelp size={16} /><span>Need a hand?</span><a href="#help">Get help</a></div>
      </div>
    </aside>
  )
}
