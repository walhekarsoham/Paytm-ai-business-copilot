import { ArrowRight, Sparkles } from 'lucide-react'
import type { DashboardSnapshot } from '../../types/merchant'

type AIInsightsProps = { insights: DashboardSnapshot['insights']; isLoading?: boolean }

export function AIInsights({ insights, isLoading = false }: AIInsightsProps) {
  return (
    <section className="panel insights-panel" id="assistant">
      <div className="panel-heading"><div className="insights-title"><span className="insights-icon"><Sparkles size={17} /></span><div><h2>AI insights</h2><p>Helpful ideas for your business</p></div></div><span className="live-pill">LIVE</span></div>
      <div className="insight-list">
        {insights.map((insight) => (
          <article className="insight-item" key={insight.title}>
            <span className={`insight-bullet ${insight.tone}`} />
            <div><span className="insight-tag">{insight.tag}</span><h3>{insight.title}</h3><p>{insight.description}</p></div>
          </article>
        ))}
        {!isLoading && insights.length === 0 && <p className="dashboard-empty-note">Insights will appear as sales and stock data are recorded.</p>}
        {isLoading && <p className="dashboard-empty-note">Loading business insights…</p>}
      </div>
      <a className="panel-link" href="#assistant">Explore all insights <ArrowRight size={15} /></a>
    </section>
  )
}
