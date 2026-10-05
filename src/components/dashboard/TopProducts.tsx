import { ArrowUpRight, MoreHorizontal } from 'lucide-react'
import type { DashboardSnapshot } from '../../types/merchant'

type TopProductsProps = { products: DashboardSnapshot['topProducts']; isLoading: boolean }

const formatMoney = (value: number) => `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

export function TopProducts({ products, isLoading }: TopProductsProps) {
  return (
    <section className="panel products-panel">
      <div className="panel-heading"><div><h2>Top products</h2><p>Your best performers this week</p></div><button className="more-button" type="button" aria-label="More product options"><MoreHorizontal size={20} /></button></div>
      <div className="product-list">
        {products.map((product) => (
          <div className="product-row" key={product.name}>
            <div className={`product-avatar ${product.tone}`}>{product.initials}</div>
            <div className="product-main"><div className="product-name">{product.name}</div><div className="product-category">{product.category}</div><div className="product-progress"><span style={{ width: `${product.share}%` }} /></div></div>
            <div className="product-result"><strong>{formatMoney(product.revenue)}</strong><span>{product.sold} sold <ArrowUpRight size={12} /></span></div>
          </div>
        ))}
        {!isLoading && products.length === 0 && <p className="dashboard-empty-note">Top products will appear after sales are recorded.</p>}
        {isLoading && <p className="dashboard-empty-note">Loading product sales…</p>}
      </div>
      <a className="panel-link" href="#products">View all products <span>→</span></a>
    </section>
  )
}
