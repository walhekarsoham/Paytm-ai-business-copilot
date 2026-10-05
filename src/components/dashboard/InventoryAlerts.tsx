import { AlertTriangle, ArrowRight, Package } from 'lucide-react'
import type { DashboardSnapshot } from '../../types/merchant'

type InventoryAlertsProps = { alerts: DashboardSnapshot['inventoryAlerts']; isLoading: boolean }

export function InventoryAlerts({ alerts, isLoading }: InventoryAlertsProps) {
  return (
    <section className="panel inventory-panel">
      <div className="panel-heading"><div><h2>Inventory alerts</h2><p>Products that need your attention</p></div><span className="alert-count"><AlertTriangle size={13} />{alerts.length} alerts</span></div>
      <div className="inventory-list">
        {alerts.map((item) => (
          <div className="inventory-row" key={item.sku}>
            <span className="inventory-product-icon"><Package size={17} /></span>
            <div className="inventory-product"><strong>{item.name}</strong><span>{item.sku}</span></div>
            <div className="inventory-stock"><strong>{item.stock} left</strong><span className={`stock-status ${item.tone}`}>{item.status}</span></div>
          </div>
        ))}
        {!isLoading && alerts.length === 0 && <p className="dashboard-empty-note">No products are at or below their stock threshold.</p>}
        {isLoading && <p className="dashboard-empty-note">Loading stock alerts…</p>}
      </div>
      <a className="panel-link" href="#inventory">Manage inventory <ArrowRight size={15} /></a>
    </section>
  )
}
