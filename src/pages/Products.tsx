import { useMemo, useState, type FormEvent } from 'react'
import { Eye, PackagePlus, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { PageHeading } from '../components/layout/PageHeading'
import type { MerchantProduct, Transaction } from '../types/merchant'

type ProductsPageProps = {
  products: MerchantProduct[]
  transactions: Transaction[]
  isLoading: boolean
  error: string | null
  onSaveProduct: (product: MerchantProduct) => Promise<void>
  onDeleteProduct: (productId: string) => Promise<void>
}

type ProductEditorProps = {
  product?: MerchantProduct
  products: MerchantProduct[]
  onSave: (product: MerchantProduct) => Promise<void>
  onCancel: () => void
}

type ProductSort = 'name' | 'category' | 'price-asc' | 'price-desc' | 'stock-asc' | 'revenue-desc'

const formatMoney = (value: number) => `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function stockLabel(product: MerchantProduct) {
  if (product.stockQuantity === 0) return { label: 'Out of stock', tone: 'out' }
  if (product.stockQuantity <= product.lowStockThreshold) return { label: 'Low stock', tone: 'low' }
  return { label: 'In stock', tone: 'healthy' }
}

function ProductEditor({ product, products, onSave, onCancel }: ProductEditorProps) {
  const categories = Array.from(new Set(products.map((item) => item.category))).sort()
  const [name, setName] = useState(product?.name ?? '')
  const [category, setCategory] = useState(product?.category ?? '')
  const [sku, setSku] = useState(product?.sku ?? '')
  const [unitPrice, setUnitPrice] = useState(product ? String(product.unitPrice) : '')
  const [costPrice, setCostPrice] = useState(product ? String(product.costPrice) : '')
  const [stockQuantity, setStockQuantity] = useState(product ? String(product.stockQuantity) : '0')
  const [lowStockThreshold, setLowStockThreshold] = useState(product ? String(product.lowStockThreshold) : '5')
  const [error, setError] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedSku = sku.trim().toUpperCase()
    const sellingPrice = Number(unitPrice)
    const purchasePrice = Number(costPrice)
    const quantity = Number(stockQuantity)
    const threshold = Number(lowStockThreshold)
    const duplicateSku = products.some((item) => item.sku.toLowerCase() === normalizedSku.toLowerCase() && item.id !== product?.id)

    if (!name.trim() || !category.trim() || !normalizedSku) {
      setError('Enter a product name, category and SKU.')
      return
    }
    if (duplicateSku) {
      setError('That SKU is already used by another product.')
      return
    }
    if (!Number.isFinite(sellingPrice) || sellingPrice <= 0 || !/^\d+(?:\.\d{1,2})?$/.test(unitPrice.trim())) {
      setError('Selling price must be greater than zero and have at most two decimal places.')
      return
    }
    if (!Number.isFinite(purchasePrice) || purchasePrice < 0 || !/^\d+(?:\.\d{1,2})?$/.test(costPrice.trim())) {
      setError('Enter a valid cost price with at most two decimal places.')
      return
    }
    if (!Number.isInteger(quantity) || quantity < 0 || !Number.isInteger(threshold) || threshold < 0) {
      setError('Stock quantity and low-stock threshold must be whole numbers of zero or more.')
      return
    }

    setIsSaving(true)
    try {
      await onSave({
        id: product?.id ?? `PRD-${Date.now()}`,
        name: name.trim(),
        category: category.trim(),
        sku: normalizedSku,
        unitPrice: sellingPrice,
        costPrice: purchasePrice,
        stockQuantity: quantity,
        lowStockThreshold: threshold,
      })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save this product.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="catalog-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel() }}>
      <section className="catalog-modal" role="dialog" aria-modal="true" aria-labelledby="product-editor-title">
        <div className="catalog-modal-heading">
          <div><span className="catalog-modal-kicker">PRODUCT CATALOG</span><h2 id="product-editor-title">{product ? 'Edit product' : 'Add product'}</h2></div>
          <button className="catalog-icon-button" type="button" aria-label="Close product form" onClick={onCancel}><X size={18} /></button>
        </div>
        <form className="catalog-form" onSubmit={handleSubmit} noValidate>
          <div className="catalog-form-grid">
            <label className="catalog-field catalog-field-wide"><span>Product name</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Toor Dal 1 kg" maxLength={80} /></label>
            <label className="catalog-field"><span>Category</span><input list="product-categories" value={category} onChange={(event) => setCategory(event.target.value)} placeholder="e.g. Pulses" maxLength={40} /><datalist id="product-categories">{categories.map((item) => <option key={item} value={item} />)}</datalist></label>
            <label className="catalog-field"><span>SKU</span><input value={sku} onChange={(event) => setSku(event.target.value)} placeholder="e.g. DAL-001" maxLength={32} /></label>
            <label className="catalog-field"><span>Selling price</span><span className="catalog-currency-field"><b>₹</b><input type="number" min="0.01" step="0.01" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} placeholder="0.00" /></span></label>
            <label className="catalog-field"><span>Cost price</span><span className="catalog-currency-field"><b>₹</b><input type="number" min="0" step="0.01" value={costPrice} onChange={(event) => setCostPrice(event.target.value)} placeholder="0.00" /></span></label>
            <label className="catalog-field"><span>Stock quantity</span><input type="number" min="0" step="1" value={stockQuantity} onChange={(event) => setStockQuantity(event.target.value)} /></label>
            <label className="catalog-field"><span>Low-stock threshold</span><input type="number" min="0" step="1" value={lowStockThreshold} onChange={(event) => setLowStockThreshold(event.target.value)} /></label>
          </div>
          {error && <p className="catalog-form-error" role="alert">{error}</p>}
          <div className="catalog-modal-actions"><button className="catalog-secondary-button" type="button" onClick={onCancel} disabled={isSaving}>Cancel</button><button className="catalog-primary-button" type="submit" disabled={isSaving}><PackagePlus size={16} />{isSaving ? 'Saving…' : product ? 'Save changes' : 'Add product'}</button></div>
        </form>
      </section>
    </div>
  )
}

export function ProductsPage({ products, transactions, isLoading, error, onSaveProduct, onDeleteProduct }: ProductsPageProps) {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [sort, setSort] = useState<ProductSort>('name')
  const [editorProduct, setEditorProduct] = useState<MerchantProduct | null | undefined>(undefined)
  const [detailProduct, setDetailProduct] = useState<MerchantProduct | null>(null)
  const [deleteProduct, setDeleteProduct] = useState<MerchantProduct | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const revenueByProduct = useMemo(() => transactions.reduce<Record<string, number>>((totals, transaction) => {
    totals[transaction.productId] = (totals[transaction.productId] ?? 0) + transaction.total
    return totals
  }, {}), [transactions])
  const salesByProduct = useMemo(() => transactions.reduce<Record<string, number>>((totals, transaction) => {
    totals[transaction.productId] = (totals[transaction.productId] ?? 0) + transaction.quantity
    return totals
  }, {}), [transactions])
  const categories = Array.from(new Set(products.map((product) => product.category))).sort()
  const lowStockCount = products.filter((product) => product.stockQuantity <= product.lowStockThreshold).length
  const visibleProducts = useMemo(() => {
    const query = search.trim().toLowerCase()
    const filtered = products.filter((product) => {
      const matchesSearch = !query || `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(query)
      return matchesSearch && (categoryFilter === 'all' || product.category === categoryFilter)
    })
    return filtered.sort((first, second) => {
      if (sort === 'category') return first.category.localeCompare(second.category) || first.name.localeCompare(second.name)
      if (sort === 'price-asc') return first.unitPrice - second.unitPrice
      if (sort === 'price-desc') return second.unitPrice - first.unitPrice
      if (sort === 'stock-asc') return first.stockQuantity - second.stockQuantity
      if (sort === 'revenue-desc') return (revenueByProduct[second.id] ?? 0) - (revenueByProduct[first.id] ?? 0)
      return first.name.localeCompare(second.name)
    })
  }, [categoryFilter, products, revenueByProduct, search, sort])

  async function saveProduct(product: MerchantProduct) {
    await onSaveProduct(product)
    setEditorProduct(undefined)
  }

  return (
    <div className="workspace-page catalog-page" aria-busy={isLoading}>
      <PageHeading title="Products" description="Manage your grocery catalog, pricing and stock details." action={<button className="catalog-primary-button" type="button" onClick={() => setEditorProduct(null)}><Plus size={16} />Add product</button>} />

      {(error || actionError) && <div className="api-error-state" role="alert">{actionError ?? error}</div>}

      <section className="catalog-metrics" aria-label="Product catalog summary">
        <article><span>Catalog products</span><strong>{products.length.toLocaleString('en-IN')}</strong><small>Active grocery items</small></article>
        <article><span>Stock units</span><strong>{products.reduce((total, product) => total + product.stockQuantity, 0).toLocaleString('en-IN')}</strong><small>Across all products</small></article>
        <article><span>Need restocking</span><strong className={lowStockCount ? 'catalog-metric-warning' : ''}>{lowStockCount.toLocaleString('en-IN')}</strong><small>At or below threshold</small></article>
      </section>

      <section className="panel catalog-panel">
        <div className="catalog-toolbar">
          <label className="catalog-search"><Search size={16} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, SKU or category" aria-label="Search products" /></label>
          <label className="catalog-select-label"><span>Category</span><select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="all">All categories</option>{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select></label>
          <label className="catalog-select-label"><span>Sort by</span><select value={sort} onChange={(event) => setSort(event.target.value as ProductSort)}><option value="name">Name</option><option value="category">Category</option><option value="price-asc">Price: low to high</option><option value="price-desc">Price: high to low</option><option value="stock-asc">Stock: low to high</option><option value="revenue-desc">Revenue: high to low</option></select></label>
        </div>
        <div className="catalog-table-scroll">
          <table className="catalog-table">
            <thead><tr><th>Product</th><th>Category</th><th>Selling price</th><th>Cost price</th><th>Stock</th><th>Sales</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {visibleProducts.map((product) => {
                const status = stockLabel(product)
                return <tr key={product.id}>
                  <td><button className="catalog-product-link" type="button" onClick={() => setDetailProduct(product)}><strong>{product.name}</strong><small>{product.sku}</small></button></td>
                  <td><span className="catalog-category-chip">{product.category}</span></td>
                  <td>{formatMoney(product.unitPrice)}</td>
                  <td>{formatMoney(product.costPrice)}</td>
                  <td><span className={`catalog-stock-status ${status.tone}`}>{product.stockQuantity} <small>{status.label}</small></span></td>
                  <td><strong className="catalog-sales-value">{formatMoney(revenueByProduct[product.id] ?? 0)}</strong><small className="catalog-sales-units">{salesByProduct[product.id] ?? 0} sold</small></td>
                  <td><div className="catalog-row-actions"><button className="catalog-icon-button" type="button" aria-label={`View ${product.name} details`} title="View details" onClick={() => setDetailProduct(product)}><Eye size={16} /></button><button className="catalog-icon-button" type="button" aria-label={`Edit ${product.name}`} title="Edit product" onClick={() => setEditorProduct(product)}><Pencil size={16} /></button><button className="catalog-icon-button danger" type="button" aria-label={`Delete ${product.name}`} title="Delete product" onClick={() => setDeleteProduct(product)}><Trash2 size={16} /></button></div></td>
                </tr>
              })}
              {!visibleProducts.length && <tr><td className="catalog-empty" colSpan={7}>{products.length ? 'No products match your search.' : 'No products yet. Add your first grocery product to get started.'}</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="catalog-table-footer">{isLoading ? 'Syncing catalog…' : `Showing ${visibleProducts.length} of ${products.length} products`}</div>
      </section>

      {editorProduct !== undefined && <ProductEditor product={editorProduct ?? undefined} products={products} onSave={saveProduct} onCancel={() => setEditorProduct(undefined)} />}

      {detailProduct && (() => {
        const productTransactions = transactions.filter((transaction) => transaction.productId === detailProduct.id).sort((first, second) => second.date.localeCompare(first.date))
        const sold = productTransactions.reduce((total, transaction) => total + transaction.quantity, 0)
        const revenue = productTransactions.reduce((total, transaction) => total + transaction.total, 0)
        return <div className="catalog-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDetailProduct(null) }}><section className="catalog-modal product-detail-modal" role="dialog" aria-modal="true" aria-labelledby="product-detail-title"><div className="catalog-modal-heading"><div><span className="catalog-modal-kicker">PRODUCT DETAILS · {detailProduct.sku}</span><h2 id="product-detail-title">{detailProduct.name}</h2><p>{detailProduct.category}</p></div><button className="catalog-icon-button" type="button" aria-label="Close product details" onClick={() => setDetailProduct(null)}><X size={18} /></button></div><div className="product-detail-metrics"><article><span>Units sold</span><strong>{sold.toLocaleString('en-IN')}</strong></article><article><span>Revenue</span><strong>{formatMoney(revenue)}</strong></article><article><span>Current stock</span><strong>{detailProduct.stockQuantity.toLocaleString('en-IN')}</strong></article><article><span>Gross margin / unit</span><strong>{formatMoney(detailProduct.unitPrice - detailProduct.costPrice)}</strong></article></div><div className="product-detail-section"><h3>Recent sales</h3>{productTransactions.length ? <div className="product-sale-list">{productTransactions.slice(0, 5).map((transaction) => <div key={transaction.id}><span><strong>{transaction.id}</strong><small>{new Date(transaction.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</small></span><span>{transaction.quantity} sold<strong>{formatMoney(transaction.total)}</strong></span></div>)}</div> : <p className="product-detail-empty">No sales have been recorded for this product yet.</p>}</div><div className="catalog-modal-actions"><button className="catalog-secondary-button" type="button" onClick={() => setDetailProduct(null)}>Close</button><button className="catalog-primary-button" type="button" onClick={() => { setEditorProduct(detailProduct); setDetailProduct(null) }}><Pencil size={15} />Edit product</button></div></section></div>
      })()}

      {deleteProduct && <div className="catalog-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDeleteProduct(null) }}><section className="catalog-modal catalog-confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-product-title"><span className="catalog-confirm-icon"><Trash2 size={19} /></span><h2 id="delete-product-title">Delete {deleteProduct.name}?</h2><p>This removes the product from your catalog and inventory. Existing sales and stock history are kept.</p><div className="catalog-modal-actions"><button className="catalog-secondary-button" type="button" onClick={() => setDeleteProduct(null)}>Keep product</button><button className="catalog-danger-button" type="button" onClick={async () => { try { await onDeleteProduct(deleteProduct.id); setDeleteProduct(null); setActionError(null) } catch (deleteError) { setActionError(deleteError instanceof Error ? deleteError.message : 'Could not delete this product.') } }}><Trash2 size={15} />Delete product</button></div></section></div>}
    </div>
  )
}