import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Search, SlidersHorizontal } from 'lucide-react'
import type { PaymentMethod, Transaction } from '../../types/merchant'

type SortField = 'date' | 'total'
type SortDirection = 'asc' | 'desc'

const formatDate = (value: string) => new Intl.DateTimeFormat('en-IN', {
  day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
}).format(new Date(value))

const formatMoney = (value: number) => `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

type RecentTransactionsProps = { transactions: Transaction[] }

export function RecentTransactions({ transactions }: RecentTransactionsProps) {
  const [search, setSearch] = useState('')
  const [paymentFilter, setPaymentFilter] = useState<'All methods' | PaymentMethod>('All methods')
  const [sortField, setSortField] = useState<SortField>('date')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const visibleTransactions = useMemo(() => {
    const query = search.trim().toLowerCase()
    return transactions
      .filter((transaction) => paymentFilter === 'All methods' || transaction.paymentMethod === paymentFilter)
      .filter((transaction) => !query || [transaction.id, transaction.productName, transaction.sku, transaction.searchText ?? '', transaction.paymentMethod].some((value) => value.toLowerCase().includes(query)))
      .sort((a, b) => {
        const order = sortField === 'date'
          ? new Date(a.date).getTime() - new Date(b.date).getTime()
          : a.total - b.total
        return sortDirection === 'asc' ? order : -order
      })
  }, [transactions, search, paymentFilter, sortField, sortDirection])

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDirection((direction) => direction === 'asc' ? 'desc' : 'asc')
    else {
      setSortField(field)
      setSortDirection(field === 'date' ? 'desc' : 'asc')
    }
  }

  const sortIcon = (field: SortField) => sortField !== field ? <ArrowUpDown size={13} /> : sortDirection === 'asc' ? <ArrowUp size={13} /> : <ArrowDown size={13} />

  return (
    <section className="panel transactions-panel" aria-labelledby="recent-transactions-title">
      <div className="panel-heading transactions-heading">
        <div><h2 id="recent-transactions-title">Recent transactions</h2><p>{visibleTransactions.length} of {transactions.length === 100 ? 'latest 100' : transactions.length} transactions</p></div>
        <span className="transactions-count"><SlidersHorizontal size={13} />Live list</span>
      </div>

      <div className="transaction-toolbar">
        <label className="transaction-search"><Search size={16} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search ID, product or SKU" aria-label="Search transactions" /></label>
        <label className="transaction-filter"><span>Payment</span><select value={paymentFilter} onChange={(event) => setPaymentFilter(event.target.value as 'All methods' | PaymentMethod)} aria-label="Filter by payment method">
          <option>All methods</option><option>UPI</option><option>Cash</option><option>Card</option><option>Net banking</option>
        </select></label>
      </div>

      <div className="table-scroll">
        <table className="transaction-table">
          <thead><tr>
            <th><button type="button" className="sort-button" onClick={() => toggleSort('date')} aria-label={`Sort by date, currently ${sortDirection === 'asc' && sortField === 'date' ? 'ascending' : 'descending'}`}>Date &amp; ID {sortIcon('date')}</button></th>
            <th>Product</th><th>Payment</th><th>Qty</th>
            <th className="amount-column"><button type="button" className="sort-button" onClick={() => toggleSort('total')} aria-label={`Sort by amount, currently ${sortDirection === 'asc' && sortField === 'total' ? 'ascending' : 'descending'}`}>Amount {sortIcon('total')}</button></th>
          </tr></thead>
          <tbody>
            {visibleTransactions.map((transaction) => (
              <tr key={transaction.id}>
                <td><strong className="transaction-id">{transaction.id}</strong><span className="transaction-date">{formatDate(transaction.date)}</span></td>
                <td><strong className="table-product-name">{transaction.productName}</strong><span className="table-product-sku">{transaction.sku}</span></td>
                <td><span className={`payment-chip ${transaction.paymentMethod.toLowerCase().replace(' ', '-')}`}>{transaction.paymentMethod}</span></td>
                <td>{transaction.quantity}</td>
                <td className="amount-column"><strong>{formatMoney(transaction.total)}</strong></td>
              </tr>
            ))}
            {visibleTransactions.length === 0 && <tr><td className="empty-transactions" colSpan={5}>{transactions.length === 0 ? 'No transactions recorded today yet.' : 'No transactions match your search. Try another keyword or payment method.'}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  )
}
