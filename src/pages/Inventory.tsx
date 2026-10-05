import { useMemo, useState, type FormEvent } from 'react'
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, Boxes, PackageCheck, Search, X } from 'lucide-react'
import { PageHeading } from '../components/layout/PageHeading'
import type { MerchantProduct, StockMovement } from '../types/merchant'

type InventoryPageProps = {
  products: MerchantProduct[]
  movements: StockMovement[]
  isLoading: boolean
  error: string | null
  onRestock: (productId: string, quantity: number, reason: string) => Promise<void>
  onSetStock: (productId: string, quantity: number, reason: string) => Promise<void>
  onUpdateThreshold: (productId: string, threshold: number) => Promise<void>
}

type StockFilter = 'all' | 'low' | 'out' | 'healthy'
type StockAction = 'restock' | 'count'

const formatDate = (date: string) => new Date(date).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })

function stockState(product: MerchantProduct) {
  if (product.stockQuantity === 0) return { label: 'Out of stock', tone: 'out' }
  if (product.stockQuantity <= product.lowStockThreshold) return { label: 'Low stock', tone: 'low' }
  return { label: 'Healthy', tone: 'healthy' }
}

export function InventoryPage({ products, movements, isLoading, error, onRestock, onSetStock, onUpdateThreshold }: InventoryPageProps) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<StockFilter>('all')
  const [selectedProduct, setSelectedProduct] = useState<MerchantProduct | null>(null)
  const [thresholdDrafts, setThresholdDrafts] = useState<Record<string, string>>({})
  const [actionError, setActionError] = useState<string | null>(null)
  const lowCount = products.filter((product) => product.stockQuantity > 0 && product.stockQuantity <= product.lowStockThreshold).length
  const outCount = products.filter((product) => product.stockQuantity === 0).length
  const healthyCount = products.filter((product) => product.stockQuantity > product.lowStockThreshold).length
  const visibleProducts = useMemo(() => products.filter((product) => {
    const query = search.trim().toLowerCase()
    const matchesSearch = !query || `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(query)
    const matchesFilter = filter === 'all'
      || (filter === 'low' && product.stockQuantity > 0 && product.stockQuantity <= product.lowStockThreshold)
      || (filter === 'out' && product.stockQuantity === 0)
      || (filter === 'healthy' && product.stockQuantity > product.lowStockThreshold)
    return matchesSearch && matchesFilter
  }).sort((first, second) => first.name.localeCompare(second.name)), [filter, products, search])
  const sortedMovements = useMemo(() => [...movements].sort((first, second) => second.date.localeCompare(first.date)), [movements])

  async function saveThreshold(productId: string) {
    const draft = thresholdDrafts[productId]
    if (draft !== undefined && /^\d+$/.test(draft)) {
      try {
        await onUpdateThreshold(productId, Number(draft))
        setActionError(null)
      } catch (updateError) {
        setActionError(updateError instanceof Error ? updateError.message : 'Could not update this stock threshold.')
      }
    }
    setThresholdDrafts((current) => {
      const next = { ...current }
      delete next[productId]
      return next
    })
  }

  return (
    <div className="workspace-page inventory-page" aria-busy={isLoading}>
      <PageHeading title="Inventory" description="Monitor grocery stock, manage replenishment and review every stock movement." />

      {(error || actionError) && <div className="api-error-state" role="alert">{actionError ?? error}</div>}

      <section className="inventory-metrics" aria-label="Inventory summary">
        <article><span className="inventory-metric-icon"><Boxes size={17} /></span><div><small>Products tracked</small><strong>{products.length.toLocaleString('en-IN')}</strong></div></article>
        <article><span className="inventory-metric-icon low"><AlertTriangle size={17} /></span><div><small>Low stock</small><strong>{lowCount.toLocaleString('en-IN')}</strong></div></article>
        <article><span className="inventory-metric-icon out"><PackageCheck size={17} /></span><div><small>Out of stock</small><strong>{outCount.toLocaleString('en-IN')}</strong></div></article>
      </section>

      <section className="panel inventory-manager-panel">
        <div className="panel-heading"><div><h2>Stock levels</h2><p>Set a product-specific alert threshold or update on-hand quantity.</p></div><span className="inventory-total-pill">{products.reduce((total, product) => total + product.stockQuantity, 0).toLocaleString('en-IN')} units</span></div>
        <div className="inventory-toolbar">
          <label className="catalog-search"><Search size={16} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search products or SKU" aria-label="Search inventory" /></label>
          <div className="inventory-filter-group" role="group" aria-label="Filter stock status"><button type="button" className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All <span>{products.length}</span></button><button type="button" className={filter === 'low' ? 'active' : ''} onClick={() => setFilter('low')}>Low <span>{lowCount}</span></button><button type="button" className={filter === 'out' ? 'active' : ''} onClick={() => setFilter('out')}>Out <span>{outCount}</span></button><button type="button" className={filter === 'healthy' ? 'active' : ''} onClick={() => setFilter('healthy')}>Healthy <span>{healthyCount}</span></button></div>
        </div>
        <div className="catalog-table-scroll">
          <table className="catalog-table inventory-table">
            <thead><tr><th>Product</th><th>Category</th><th>On hand</th><th>Status</th><th>Alert at</th><th aria-label="Actions" /></tr></thead>
            <tbody>{visibleProducts.map((product) => {
              const status = stockState(product)
              return <tr key={product.id}>
                <td><strong className="inventory-product-name">{product.name}</strong><small className="catalog-sales-units">{product.sku}</small></td>
                <td>{product.category}</td>
                <td><strong className="inventory-quantity">{product.stockQuantity}</strong><small className="catalog-sales-units">units</small></td>
                <td><span className={`catalog-stock-status ${status.tone}`}>{status.label}</span></td>
                <td><label className="threshold-input"><input aria-label={`Low-stock threshold for ${product.name}`} type="number" min="0" step="1" value={thresholdDrafts[product.id] ?? String(product.lowStockThreshold)} onChange={(event) => setThresholdDrafts((current) => ({ ...current, [product.id]: event.target.value }))} onBlur={() => { void saveThreshold(product.id) }} /><span>units</span></label></td>
                <td><button className="inventory-update-button" type="button" onClick={() => setSelectedProduct(product)}><ArrowDownToLine size={14} />Update stock</button></td>
              </tr>
            })}{!visibleProducts.length && <tr><td className="catalog-empty" colSpan={6}>{products.length ? 'No inventory items match your filter.' : 'No products are in the catalog yet.'}</td></tr>}</tbody>
          </table>
        </div>
        {isLoading && <div className="catalog-table-footer">Syncing stock levels…</div>}
      </section>

      <section className="panel movement-panel">
        <div className="panel-heading"><div><h2>Stock movement history</h2><p>Opening balances, restocks, adjustments and recorded sales.</p></div><span className="movement-count">{movements.length} movements</span></div>
        <div className="catalog-table-scroll movement-table-scroll"><table className="catalog-table movement-table"><thead><tr><th>Date</th><th>Product</th><th>Movement</th><th>Reason</th></tr></thead><tbody>{sortedMovements.map((movement) => <tr key={movement.id}><td><span className="movement-date">{formatDate(movement.date)}</span></td><td><strong className="inventory-product-name">{movement.productName}</strong></td><td><span className={`movement-quantity ${movement.quantity < 0 ? 'negative' : 'positive'}`}>{movement.quantity > 0 ? '+' : ''}{movement.quantity} units</span></td><td><span className="movement-reason">{movement.reason}</span></td></tr>)}{!sortedMovements.length && <tr><td className="catalog-empty" colSpan={4}>Stock movements will appear here.</td></tr>}</tbody></table></div>
      </section>

      {selectedProduct && <StockUpdateDialog key={selectedProduct.id} product={selectedProduct} onCancel={() => setSelectedProduct(null)} onRestock={async (quantity, reason) => { await onRestock(selectedProduct.id, quantity, reason); setSelectedProduct(null) }} onSetStock={async (quantity, reason) => { await onSetStock(selectedProduct.id, quantity, reason); setSelectedProduct(null) }} />}
    </div>
  )
}

type StockUpdateDialogProps = {
  product: MerchantProduct
  onCancel: () => void
  onRestock: (quantity: number, reason: string) => Promise<void>
  onSetStock: (quantity: number, reason: string) => Promise<void>
}

function StockUpdateDialog({ product, onCancel, onRestock, onSetStock }: StockUpdateDialogProps) {
  const [action, setAction] = useState<StockAction>('restock')
  const [quantity, setQuantity] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = Number(quantity)
    if (!Number.isInteger(value) || value < 0 || (action === 'restock' && value === 0)) {
      setError(action === 'restock' ? 'Enter a restock quantity greater than zero.' : 'Enter a whole-number stock count of zero or more.')
      return
    }
    if (action === 'count' && value === product.stockQuantity) {
      setError('The counted quantity matches the current stock.')
      return
    }
    const movementReason = reason.trim() || (action === 'restock' ? 'Supplier restock' : 'Physical stock count')
    setIsSaving(true)
    try {
      if (action === 'restock') await onRestock(value, movementReason)
      else await onSetStock(value, movementReason)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not update stock.')
    } finally {
      setIsSaving(false)
    }
  }

  return <div className="catalog-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !isSaving) onCancel() }}><section className="catalog-modal stock-update-modal" role="dialog" aria-modal="true" aria-labelledby="stock-update-title"><div className="catalog-modal-heading"><div><span className="catalog-modal-kicker">{product.sku} · {product.stockQuantity} UNITS ON HAND</span><h2 id="stock-update-title">Update {product.name}</h2></div><button className="catalog-icon-button" type="button" aria-label="Close stock update" onClick={onCancel} disabled={isSaving}><X size={18} /></button></div><form className="catalog-form" onSubmit={handleSubmit} noValidate><div className="stock-action-tabs" role="group" aria-label="Stock action"><button className={action === 'restock' ? 'active' : ''} type="button" onClick={() => { setAction('restock'); setQuantity(''); setError('') }} disabled={isSaving}><ArrowDownToLine size={15} />Record restock</button><button className={action === 'count' ? 'active' : ''} type="button" onClick={() => { setAction('count'); setQuantity(''); setError('') }} disabled={isSaving}><ArrowUpFromLine size={15} />Set counted stock</button></div><label className="catalog-field"><span>{action === 'restock' ? 'Units received' : 'Counted units on hand'}</span><input autoFocus type="number" min="0" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder={action === 'restock' ? 'e.g. 24' : String(product.stockQuantity)} /></label><label className="catalog-field"><span>Reason <small>(optional)</small></span><input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={100} placeholder={action === 'restock' ? 'e.g. Supplier delivery' : 'e.g. Damaged items removed'} /></label>{error && <p className="catalog-form-error" role="alert">{error}</p>}<div className="catalog-modal-actions"><button className="catalog-secondary-button" type="button" onClick={onCancel} disabled={isSaving}>Cancel</button><button className="catalog-primary-button" type="submit" disabled={isSaving}><ArrowDownToLine size={15} />{isSaving ? 'Saving…' : action === 'restock' ? 'Record restock' : 'Save stock count'}</button></div></form></section></div>
}