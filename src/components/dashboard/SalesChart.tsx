import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { AnalyticsPeriod, DashboardSnapshot } from '../../types/merchant'

const formatRupees = (value: number) => value >= 1000 ? `₹${Math.round(value / 1000)}k` : `₹${Math.round(value)}`
const formatMoney = (value: number) => `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const periodLabels: Record<AnalyticsPeriod, string> = { '7d': 'Last 7 days', '30d': 'Last 30 days', '12m': 'Last 12 months' }

type SalesChartProps = {
  period: AnalyticsPeriod
  salesSeries: DashboardSnapshot['salesSeries']
  totalSales: number
  salesChangePercent: number | null
  isLoading: boolean
  onPeriodChange: (period: AnalyticsPeriod) => void
}

export function SalesChart({ period, salesSeries, totalSales, salesChangePercent, isLoading, onPeriodChange }: SalesChartProps) {
  const trendLabel = salesChangePercent === null
    ? (totalSales ? 'New activity' : 'No comparison')
    : `${salesChangePercent >= 0 ? '+' : ''}${salesChangePercent.toFixed(1)}%`

  return (
    <section className="panel sales-panel">
      <div className="panel-heading sales-heading">
        <div><h2>Sales overview</h2><p>Recorded grocery sales by period</p></div>
        <select className="period-select" value={period} onChange={(event) => onPeriodChange(event.target.value as AnalyticsPeriod)} aria-label="Analytics period">
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="12m">Last 12 months</option>
        </select>
      </div>
      <div className="sales-summary"><strong>{formatMoney(totalSales)}</strong><span className={`trend ${salesChangePercent === null || salesChangePercent >= 0 ? 'positive' : 'negative'}`}>{trendLabel}</span><span className="summary-period">{periodLabels[period]}</span></div>
      <div className="chart-legend"><span><i className="legend-dot current" />Selected period</span><span><i className="legend-dot previous" />Previous period</span></div>
      {isLoading ? <div className="chart-empty">Loading sales history…</div> : salesSeries.every((point) => point.current === 0 && point.previous === 0) ? <div className="chart-empty">No sales in this period.</div> : <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={salesSeries} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="currentFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--brand-accent)" stopOpacity={0.18} /><stop offset="100%" stopColor="var(--brand-accent)" stopOpacity={0} /></linearGradient>
                <linearGradient id="previousFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a5b4fc" stopOpacity={0.12} /><stop offset="100%" stopColor="#a5b4fc" stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="#edf0f5" strokeDasharray="4 5" />
              <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#98a2b3', fontSize: 12 }} dy={10} interval={period === '30d' ? 4 : 0} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: '#98a2b3', fontSize: 11 }} tickFormatter={formatRupees} />
              <Tooltip formatter={(value) => [`₹${Number(value).toLocaleString('en-IN')}`, '']} contentStyle={{ border: '1px solid #edf0f5', borderRadius: 12, boxShadow: '0 8px 24px #172b4d12' }} />
              <Area type="monotone" dataKey="previous" stroke="#a5b4fc" strokeWidth={2} strokeDasharray="5 5" fill="url(#previousFill)" />
              <Area type="monotone" dataKey="current" stroke="var(--brand-accent)" strokeWidth={2.5} fill="url(#currentFill)" activeDot={{ r: 5, strokeWidth: 3, stroke: 'var(--surface)' }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>}
    </section>
  )
}
