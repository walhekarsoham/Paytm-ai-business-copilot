import { BadgeCheck, Megaphone, PackageCheck, Settings2, Sparkles } from 'lucide-react'
import { PageHeading } from '../components/layout/PageHeading'
import { AICopilot } from './AICopilot'
import { InventoryPage } from './Inventory'
import { ProductsPage } from './Products'
import type { AppPage, Campaign, DashboardSnapshot, MerchantProduct, MerchantSession, StockMovement, Transaction } from '../types/merchant'

type WorkspacePageProps = {
  page: Exclude<AppPage, 'Overview' | 'Sales'>
  products: MerchantProduct[]
  transactions: Transaction[]
  movements: StockMovement[]
  campaigns: Campaign[]
  dashboard: DashboardSnapshot | null
  merchant: MerchantSession
  isLoading: boolean
  error: string | null
  onSaveProduct: (product: MerchantProduct) => Promise<void>
  onDeleteProduct: (productId: string) => Promise<void>
  onRestock: (productId: string, quantity: number, reason: string) => Promise<void>
  onSetStock: (productId: string, quantity: number, reason: string) => Promise<void>
  onUpdateThreshold: (productId: string, threshold: number) => Promise<void>
}

const pageContent: Record<WorkspacePageProps['page'], { title: string; description: string }> = {
  Products: { title: 'Products', description: 'Review your best-performing products and product mix.' },
  Inventory: { title: 'Inventory', description: 'Keep an eye on stock levels and restock items before they run out.' },
  'AI Copilot': { title: 'AI Copilot', description: 'Practical, data-informed suggestions to help grow your business.' },
  Campaigns: { title: 'Campaigns', description: 'Plan and track promotions for your customers.' },
  Settings: { title: 'Settings', description: 'Business workspace preferences and account details.' },
}

export function WorkspacePage({ page, products, transactions, movements, campaigns, dashboard, merchant, isLoading, error, onSaveProduct, onDeleteProduct, onRestock, onSetStock, onUpdateThreshold }: WorkspacePageProps) {
  if (page === 'Products') return <ProductsPage products={products} transactions={transactions} isLoading={isLoading} error={error} onSaveProduct={onSaveProduct} onDeleteProduct={onDeleteProduct} />
  if (page === 'Inventory') return <InventoryPage products={products} movements={movements} isLoading={isLoading} error={error} onRestock={onRestock} onSetStock={onSetStock} onUpdateThreshold={onUpdateThreshold} />
  if (page === 'AI Copilot') return <AICopilot merchantName={merchant.businessName} />

  const content = pageContent[page]
  return (
    <div className="workspace-page">
      <PageHeading title={content.title} description={content.description} />

      {error && <div className="api-error-state" role="alert">{error}</div>}
      {page === 'Campaigns' && (
        <section className="panel campaigns-panel">
          <div className="panel-heading"><div><h2>Campaign workspace</h2><p>Campaigns for {merchant.businessName}</p></div><span className="campaign-icon"><Megaphone size={18} /></span></div>
          <div className="campaign-list">
            {campaigns.map((campaign) => <article className="campaign-row" key={campaign.name}>
              <span className={`campaign-mark ${campaign.tone}`}><Megaphone size={16} /></span>
              <div className="campaign-details"><strong>{campaign.name}</strong><span>{campaign.channel} · {campaign.reach}</span></div>
              <span className={`campaign-status ${campaign.status.toLowerCase()}`}>{campaign.status}</span>
            </article>)}
            {isLoading && <p className="dashboard-empty-note">Loading campaigns…</p>}
            {!isLoading && campaigns.length === 0 && <p className="dashboard-empty-note">No campaigns are available for this merchant yet.</p>}
          </div>
          <div className="campaign-note"><Sparkles size={15} /><span>Campaign examples are connected to this merchant account.</span></div>
        </section>
      )}

      {page === 'Settings' && (
        <section className="panel settings-panel">
          <div className="panel-heading"><div><h2>Business profile</h2><p>Basic details for your merchant workspace</p></div><span className="campaign-icon"><Settings2 size={18} /></span></div>
          <div className="settings-list">
            <div className="settings-row"><span>Business name</span><strong>{merchant.businessName}</strong></div>
            <div className="settings-row"><span>Business type</span><strong>Grocery merchant</strong></div>
            <div className="settings-row"><span>Email</span><strong>{merchant.email}</strong></div>
            <div className="settings-row"><span>Workspace status</span><strong className="settings-verified"><BadgeCheck size={15} />Active</strong></div>
            <div className="settings-row"><span>Inventory sync</span><strong className="settings-verified"><PackageCheck size={15} />Database catalog connected</strong></div>
          </div>
          <p className="settings-note">This profile is read from your authenticated merchant account.</p>
        </section>
      )}
    </div>
  )
}
