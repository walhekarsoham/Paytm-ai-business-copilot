import { ArrowUpRight, ReceiptText } from 'lucide-react'
import { RecentTransactions } from '../components/sales/RecentTransactions'
import { TransactionForm } from '../components/sales/TransactionForm'
import { PageHeading } from '../components/layout/PageHeading'
import type { MerchantProduct, SaleInput, Transaction } from '../types/merchant'

type SalesProps = {
  transactions: Transaction[]
  products: MerchantProduct[]
  onAddTransaction: (sale: SaleInput) => Promise<Transaction>
  isLoading: boolean
  error: string | null
}

export function Sales({ transactions, products, onAddTransaction, isLoading, error }: SalesProps) {
  const totalRecorded = transactions.reduce((sum, transaction) => sum + transaction.total, 0)

  return (
    <div className="workspace-page sales-page">
      <PageHeading title="Sales & transactions" description="Record in-store sales and review today's transactions." action={<span className="sales-live-tag"><span />{isLoading ? 'Syncing…' : 'Today · synced to backend'}</span>} />

      {error && <div className="api-error-state" role="alert">{error}</div>}

      <section className="sales-metrics" aria-label="Sales page summary">
        <article className="sales-metric"><span className="sales-metric-icon"><ReceiptText size={17} /></span><div><span>Today's transactions</span><strong>{transactions.length.toLocaleString('en-IN')}</strong></div></article>
        <article className="sales-metric"><span className="sales-metric-icon sales-metric-green"><ArrowUpRight size={17} /></span><div><span>Today's transaction value</span><strong>₹{totalRecorded.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></div></article>
      </section>

      <div className="sales-workspace-grid">
        <TransactionForm products={products} onSave={onAddTransaction} isLoading={isLoading} />
        <RecentTransactions transactions={transactions} />
      </div>
      <p className="local-data-note">Sales are recorded to your merchant account and inventory is updated with each completed sale.</p>
    </div>
  )
}
