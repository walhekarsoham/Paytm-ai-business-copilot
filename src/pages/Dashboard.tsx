import { ArrowDownToLine, CreditCard, ShoppingBag, Users, Wallet } from 'lucide-react'
import { AIInsights } from '../components/dashboard/AIInsights'
import { InventoryAlerts } from '../components/dashboard/InventoryAlerts'
import { SalesChart } from '../components/dashboard/SalesChart'
import { StatCard } from '../components/dashboard/StatCard'
import { TopProducts } from '../components/dashboard/TopProducts'
import type { AnalyticsPeriod, DashboardSnapshot } from '../types/merchant'

type DashboardProps = {
  data: DashboardSnapshot | null
  period: AnalyticsPeriod
  isLoading: boolean
  error: string | null
  onPeriodChange: (period: AnalyticsPeriod) => void
}

const formatMoney = (amount: number, fractionDigits = 0) => `₹${amount.toLocaleString('en-IN', { minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits })}`
const periodLabels: Record<AnalyticsPeriod, string> = { '7d': 'last 7 days', '30d': 'last 30 days', '12m': 'last 12 months' }

export function Dashboard({ data, period, isLoading, error, onPeriodChange }: DashboardProps) {
  const totalSales = data?.totalSales ?? 0
  const totalOrders = data?.totalOrders ?? 0
  const customers = data?.customers ?? 0
  const averageOrderValue = data?.averageOrderValue ?? 0
  const salesChange = data?.salesChangePercent ?? null
  const salesChangeLabel = salesChange === null
    ? (totalSales > 0 ? 'New activity' : 'No comparison')
    : `${salesChange >= 0 ? '+' : ''}${salesChange.toFixed(1)}%`

  return (
    <div className="dashboard-page" id="overview" aria-busy={isLoading}>
      <section className="welcome-row">
        <div><div className="eyebrow">MERCHANT OVERVIEW</div><h1>Business at a glance <span>✦</span></h1><p>Here’s what’s happening with your grocery store today.</p></div>
        <button className="export-button" type="button"><ArrowDownToLine size={16} />Export report</button>
      </section>

      {error && <div className="api-error-state" role="alert">{error}</div>}

      <section className="stats-grid" aria-label="Store performance summary">
        <StatCard label="Total sales" value={isLoading && !data ? 'Loading…' : formatMoney(totalSales)} change={salesChangeLabel} comparison={`vs previous ${periodLabels[period]}`} positive={salesChange === null || salesChange >= 0} icon={<Wallet size={18} />} tone="teal" />
        <StatCard label="Total orders" value={isLoading && !data ? 'Loading…' : totalOrders.toLocaleString('en-IN')} change="Orders" comparison={periodLabels[period]} icon={<ShoppingBag size={18} />} tone="blue" />
        <StatCard label="Customers" value={isLoading && !data ? 'Loading…' : customers.toLocaleString('en-IN')} change="Distinct shoppers" comparison={periodLabels[period]} icon={<Users size={18} />} tone="purple" />
        <StatCard label="Avg. order value" value={isLoading && !data ? 'Loading…' : formatMoney(averageOrderValue, 2)} change="Per order" comparison={periodLabels[period]} icon={<CreditCard size={18} />} tone="orange" />
      </section>

      <section className="primary-grid"><SalesChart period={period} salesSeries={data?.salesSeries ?? []} totalSales={totalSales} salesChangePercent={salesChange} isLoading={isLoading} onPeriodChange={onPeriodChange} /><TopProducts products={data?.topProducts ?? []} isLoading={isLoading} /></section>
      <section className="secondary-grid"><AIInsights insights={data?.insights ?? []} isLoading={isLoading} /><InventoryAlerts alerts={data?.inventoryAlerts ?? []} isLoading={isLoading} /></section>
      <footer className="page-footer">© 2026 Paytm for Business <span>•</span> Your business, moving forward.</footer>
    </div>
  )
}
