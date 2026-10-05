import type { ReactNode } from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

type StatCardProps = {
  label: string
  value: string
  change: string
  comparison: string
  icon: ReactNode
  tone: 'teal' | 'blue' | 'purple' | 'orange'
  positive?: boolean
}

export function StatCard({ label, value, change, comparison, icon, tone, positive = true }: StatCardProps) {
  return (
    <article className="stat-card">
      <div className="stat-card-top"><span className="stat-label">{label}</span><span className={`stat-icon ${tone}`}>{icon}</span></div>
      <div className="stat-value">{value}</div>
      <div className="stat-footnote">
        <span className={`trend ${positive ? 'positive' : 'negative'}`}>
          {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{change}
        </span>
        <span>{comparison}</span>
      </div>
    </article>
  )
}
