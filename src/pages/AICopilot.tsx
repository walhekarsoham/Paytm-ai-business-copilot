import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Lightbulb, LoaderCircle, MessageCircle, RefreshCw, Send, Sparkles } from 'lucide-react'
import { api, type CopilotAnalysis, type CopilotChatMessage, type CopilotMetric, type CopilotRecommendation } from '../lib/apiClient'
import { PageHeading } from '../components/layout/PageHeading'

type AICopilotProps = { merchantName: string }

function formatMetric(metric: CopilotMetric) {
  if (metric.unit === 'INR') {
    const amount = Number(metric.value)
    return `Rs ${amount.toLocaleString('en-IN', { minimumFractionDigits: amount % 1 ? 2 : 0, maximumFractionDigits: 2 })}`
  }
  if (metric.unit === '%') return `${metric.value}%`
  return metric.unit ? `${metric.value} ${metric.unit}` : String(metric.value)
}

function formatOpportunityValue(key: string, value: number | string) {
  const numericValue = Number(value)
  if (!Number.isNaN(numericValue) && /revenue|value|spend/i.test(key)) {
    return `Rs ${numericValue.toLocaleString('en-IN', { minimumFractionDigits: numericValue % 1 ? 2 : 0, maximumFractionDigits: 2 })}`
  }
  if (!Number.isNaN(numericValue) && /percent|growth/i.test(key)) return `${numericValue}%`
  return String(value)
}

function formatMetricName(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
}

const suggestedPrompts = ['How are my sales?', 'What should I restock?', 'Show my top products', 'How can I increase sales?']

export function AICopilot({ merchantName }: AICopilotProps) {
  const [analysis, setAnalysis] = useState<CopilotAnalysis | null>(null)
  const [recommendations, setRecommendations] = useState<CopilotRecommendation[]>([])
  const [chatMessages, setChatMessages] = useState<CopilotChatMessage[]>([])
  const [question, setQuestion] = useState('')
  const [isChatting, setIsChatting] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement | null>(null)

  async function analyze(nextQuestion?: string) {
    setIsLoading(true)
    setError(null)
    try {
      const [nextAnalysis, recommendationResult] = await Promise.all([
        api.aiCopilot.analyze(nextQuestion),
        api.aiCopilot.recommendations(),
      ])
      setAnalysis(nextAnalysis)
      setRecommendations(recommendationResult.recommendations)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not analyze merchant data. Try again.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void analyze()
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [chatMessages, isChatting])

  async function sendChat(messageText?: string) {
    const message = (messageText ?? question).trim()
    if (!message || isChatting) return
    const nextMessages: CopilotChatMessage[] = [...chatMessages, { role: 'merchant', content: message }]
    setChatMessages(nextMessages)
    setQuestion('')
    setIsChatting(true)
    setError(null)
    try {
      const response = await api.aiCopilot.chat(message, chatMessages)
      setChatMessages([...nextMessages, { role: 'ai', content: response.answer }])
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not ask Copilot. Try again.')
    } finally {
      setIsChatting(false)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await sendChat()
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendChat()
    }
  }

  const visibleRecommendations = recommendations.length ? recommendations : analysis?.recommendedActions ?? []

  return (
    <div className="workspace-page ai-copilot-page" aria-busy={isLoading}>
      <PageHeading
        title="AI Copilot"
        description="Your AI business partner, grounded in your sales and stock data."
        action={<button className="ai-refresh-button" type="button" onClick={() => { void analyze(question) }} disabled={isLoading}><RefreshCw size={15} className={isLoading ? 'ai-refresh-spinning' : ''} />Refresh analysis</button>}
      />

      <section className="ai-copilot-welcome">
        <div className="ai-copilot-icon"><Sparkles size={19} /></div>
        <div><span className="ai-copilot-eyebrow">AI BUSINESS PARTNER</span><h2>{greeting()}, {merchantName}</h2><p>Here is what I found in your business:</p></div>
      </section>

      <section className="panel ai-chat-panel">
        <div className="ai-chat-shell">
          <div className="ai-chat-list">
          {chatMessages.length ? chatMessages.map((message, index) => <div className={`ai-chat-message ${message.role}`} key={`${message.role}-${index}`}>
            <span>{message.role === 'merchant' ? 'Merchant' : 'AI'}</span>
            <p>{message.content}</p>
          </div>) : <div className="ai-chat-empty">
            <div className="ai-copilot-icon"><Sparkles size={20} /></div>
            <h2>AI Business Partner</h2>
            <p>How can I help you grow your business today?</p>
            <div className="ai-prompt-chips">
              {suggestedPrompts.map((prompt) => <button type="button" key={prompt} onClick={() => { void sendChat(prompt) }}>{prompt}</button>)}
            </div>
          </div>}
          {isChatting && <div className="ai-chat-message ai"><span>AI</span><p>Checking your business data...</p></div>}
          <div ref={chatEndRef} />
          </div>
          <form className="ai-chat-composer" onSubmit={handleSubmit}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              maxLength={800}
              rows={1}
              placeholder="Message your AI business partner..."
              aria-label="Message your AI business partner"
            />
            <button className="ai-send-button" type="submit" disabled={isLoading || isChatting || !question.trim()} aria-label="Send message"><Send size={17} /></button>
          </form>
        </div>
      </section>

      {error && <div className="api-error-state" role="alert">{error}</div>}

      {isLoading && !analysis ? <div className="ai-loading-state"><LoaderCircle size={18} className="ai-refresh-spinning" /><span>Analyzing your merchant data...</span></div> : analysis && <>
        <section className="panel ai-summary-panel">
          <div className="ai-section-heading"><span className="ai-section-icon summary"><Sparkles size={16} /></span><div><h2>Business Summary</h2><p>Based on summarized merchant records</p></div><span className="ai-source-pill">{analysis.provider === 'grounded-rules' ? 'LIVE DATA' : 'AI ANALYSIS'}</span></div>
          <p className="ai-summary-copy">{analysis.summary}</p>
          <div className="ai-evidence-grid">
            {analysis.insights.flatMap((insight) => insight.supportingMetrics).slice(0, 6).map((metric) => <div className="ai-evidence-item" key={metric.key}><span>{metric.label}</span><strong>{formatMetric(metric)}</strong></div>)}
          </div>
        </section>

        <section className="panel ai-results-panel">
          <div className="ai-section-heading"><span className="ai-section-icon insight"><Lightbulb size={16} /></span><div><h2>Key Insights</h2><p>Findings supported by your data</p></div></div>
          <div className="ai-card-list">
            {analysis.insights.map((insight) => <article className="ai-result-row" key={insight.title}>
              <span className={`ai-severity-dot ${insight.severity}`} />
              <div className="ai-result-copy"><strong>{insight.title}</strong><p>{insight.explanation}</p><div className="ai-metric-tags">{insight.supportingMetrics.map((metric) => <span key={metric.key}>{metric.label}: <b>{formatMetric(metric)}</b></span>)}</div></div>
            </article>)}
            {!analysis.insights.length && <p className="dashboard-empty-note">There is not enough sales or stock data for insights yet.</p>}
          </div>
        </section>

        <section className="panel ai-results-panel">
          <div className="ai-section-heading"><span className="ai-section-icon opportunity"><ArrowUpRight size={16} /></span><div><h2>Growth Opportunities</h2><p>Potential improvements to review</p></div></div>
          <div className="ai-card-list">
            {analysis.opportunities.map((opportunity) => <article className="ai-result-row" key={opportunity.title}>
              <span className={`ai-severity-dot ${opportunity.severity}`} />
              <div className="ai-result-copy">
                <strong>{opportunity.title}</strong>
                <p>{opportunity.reason}</p>
                <small>{opportunity.recommendedAction}</small>
                <div className="ai-metric-tags">{Object.entries(opportunity.metrics).map(([key, value]) => <span key={key}>{formatMetricName(key)}: <b>{formatOpportunityValue(key, value)}</b></span>)}</div>
              </div>
            </article>)}
            {!analysis.opportunities.length && <p className="dashboard-empty-note">No additional growth opportunities were identified from the available data.</p>}
          </div>
        </section>

        <section className="panel ai-results-panel">
          <div className="ai-section-heading"><span className="ai-section-icon action"><ArrowDownRight size={16} /></span><div><h2>Recommended Actions</h2><p>Suggestions only; no business actions are executed by Copilot</p></div></div>
          <div className="ai-recommendation-list">
            {visibleRecommendations.map((recommendation) => <article className="ai-recommendation-row" key={`${recommendation.actionType}-${recommendation.title}`}>
              <div className="ai-recommendation-copy">
                <span className="ai-action-type">{recommendation.actionType.replaceAll('_', ' ')}</span>
                <strong>{recommendation.title}</strong>
                <p>{recommendation.whatIsHappening || recommendation.reason}</p>
                <small>Why it matters: {recommendation.whyItMatters || recommendation.explanation || recommendation.reason}</small>
                <small>Recommended action: {recommendation.recommendedAction || recommendation.action || recommendation.title}</small>
                <small>Expected impact: {recommendation.expectedImpact}</small>
                <div className="ai-metric-tags">
                  {Object.entries(recommendation.supportingNumbers || recommendation.metrics || {}).map(([key, value]) => <span key={key}>{formatMetricName(key)}: <b>{formatOpportunityValue(key, value)}</b></span>)}
                  {recommendation.supportingMetrics.map((metric) => <span key={metric.key}>{metric.label}: <b>{formatMetric(metric)}</b></span>)}
                </div>
              </div>
              <span className="ai-confirmation-pill"><AlertTriangle size={12} />{recommendation.requiresApproval || recommendation.requiresConfirmation ? `Approval required - ${Math.round(recommendation.confidence * 100)}% confidence` : 'Suggestion'}</span>
            </article>)}
            {!visibleRecommendations.length && <p className="dashboard-empty-note">No actions are recommended from the current evidence.</p>}
          </div>
        </section>
      </>}
    </div>
  )
}
