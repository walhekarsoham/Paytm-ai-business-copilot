import { Bell, LogOut, Search } from 'lucide-react'
import type { AppPage, MerchantSession } from '../../types/merchant'

type HeaderProps = { pageTitle: AppPage; merchant: MerchantSession; onLogout: () => void }

export function Header({ pageTitle, merchant, onLogout }: HeaderProps) {
  const initials = merchant.businessName.split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
  return (
    <header className="topbar">
      <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-separator">/</span><strong>{pageTitle}</strong></div>
      <div className="topbar-actions">
        <label className="search-box">
          <Search size={17} />
          <input type="search" placeholder="Search anything" aria-label="Search anything" />
          <kbd>⌘ K</kbd>
        </label>
        <button className="icon-button notification-button" type="button" aria-label="Notifications"><Bell size={18} /><span /></button>
        <span className="topbar-divider" />
        <button className="icon-button logout-button" type="button" title="Sign out" aria-label={`Sign out ${merchant.businessName}`} onClick={onLogout}><LogOut size={17} /></button>
        <div className="profile-button"><span className="profile-avatar">{initials}</span><span className="profile-name"><strong>{merchant.businessName}</strong><small>{merchant.email}</small></span></div>
      </div>
    </header>
  )
}
