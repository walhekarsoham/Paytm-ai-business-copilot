import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Check, CircleAlert, Mic, MicOff, Plus, Trash2 } from 'lucide-react'
import type { MerchantProduct, PaymentMethod, SaleInput, Transaction } from '../../types/merchant'

const paymentMethods: PaymentMethod[] = ['UPI', 'Cash', 'Card', 'Net banking']
const numberWords: Record<string, number> = {
  a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
}
const productUnitWords = new Set(['kg', 'kgs', 'kilo', 'kilos', 'kilogram', 'kilograms', 'g', 'gram', 'grams', 'packet', 'packets', 'pack', 'packs', 'piece', 'pieces', 'pc', 'pcs', 'bottle', 'bottles', 'litre', 'litres', 'liter', 'liters', 'l', 'ml'])

type BillingMode = 'manual' | 'voice'
type RequestedQuantity = { kind: 'count' | 'mass' | 'volume'; amount: number; baseAmount: number }
type BillingLine = { id: string; productId: string; quantity: number; spokenName: string; requested?: RequestedQuantity; matchError?: string }
type SpeechAlternativeLike = { transcript: string }
type SpeechResultLike = ArrayLike<SpeechAlternativeLike> & { isFinal: boolean }
type SpeechEventLike = { results: ArrayLike<SpeechResultLike> }
type SpeechErrorLike = { error: string }
type SpeechRecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: SpeechEventLike) => void) | null
  onerror: ((event: SpeechErrorLike) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type SpeechWindow = Window & {
  SpeechRecognition?: new () => SpeechRecognitionLike
  webkitSpeechRecognition?: new () => SpeechRecognitionLike
}

type TransactionFormProps = {
  products: MerchantProduct[]
  onSave: (sale: SaleInput) => Promise<Transaction>
  isLoading?: boolean
}

let lineSequence = 0

function newLine(spokenName = ''): BillingLine {
  lineSequence += 1
  return { id: `${Date.now()}-${lineSequence}`, productId: '', quantity: 1, spokenName }
}

function singularToken(token: string): string {
  if (token.length > 4 && token.endsWith('ies')) return `${token.slice(0, -3)}y`
  if (token.length > 3 && token.endsWith('s')) return token.slice(0, -1)
  return token
}

function normalizedTokens(value: string): string[] {
  return [...new Set(value.toLowerCase()
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\b\d+(?:\.\d+)?\s*(?:kg|kgs|kilo|kilos|kilograms?|g|grams?|ml|l|litres?|liters?|pcs?)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter((token) => token && !productUnitWords.has(token) && !['of', 'the', 'and', 'a', 'an'].includes(token) && !/^\d+$/.test(token))
    .map(singularToken))]
}

function bestProductMatch(query: string, products: MerchantProduct[], requested: RequestedQuantity): MerchantProduct | null {
  const queryTokens = normalizedTokens(query)
  if (!queryTokens.length) return null
  const ranked = products.map((product) => {
    const productTokens = normalizedTokens(`${product.name} ${product.sku}`)
    const matchedTokens = queryTokens.filter((token) => productTokens.includes(token)).length
    const score = matchedTokens ? (2 * matchedTokens) / (queryTokens.length + productTokens.length) : 0
    const quantityMatch = quantityForProduct(requested, product)
    const unitFit = requested.kind === 'count' || !quantityMatch.error ? 1 : 0
    const packPreference = unitFit && requested.kind !== 'count' ? 1 / quantityMatch.quantity : 0
    return { product, matchedTokens, score, unitFit, packPreference }
  }).sort((first, second) => second.unitFit - first.unitFit || second.packPreference - first.packPreference || second.score - first.score)
  const candidates = ranked.filter((candidate) => candidate.matchedTokens === queryTokens.length)
  const best = candidates[0]
  const runnerUp = candidates[1]
  if (!best || (runnerUp && best.unitFit === runnerUp.unitFit && best.packPreference === runnerUp.packPreference && best.score - runnerUp.score < 0.12)) return null
  return best.product
}

function parseRequestedQuantity(expression: string): RequestedQuantity {
  const normalized = expression.toLowerCase().trim().replace(/\s+/g, ' ')
  if (/^half\s+(?:a\s+)?(?:kilo|kilogram|kg|kgs)$/.test(normalized)) return { kind: 'mass', amount: 0.5, baseAmount: 500 }
  const parsed = normalized.match(/^(\d+(?:\.\d+)?|[a-z]+)(?:\s+([a-z]+))?$/)
  const amount = parsed ? (/^\d/.test(parsed[1]) ? Number(parsed[1]) : numberWords[parsed[1]] ?? 1) : 1
  const unit = parsed?.[2] ?? ''
  if (['kg', 'kgs', 'kilo', 'kilos', 'kilogram', 'kilograms'].includes(unit)) return { kind: 'mass', amount, baseAmount: amount * 1000 }
  if (['g', 'gram', 'grams'].includes(unit)) return { kind: 'mass', amount, baseAmount: amount }
  if (['l', 'litre', 'litres', 'liter', 'liters'].includes(unit)) return { kind: 'volume', amount, baseAmount: amount * 1000 }
  if (unit === 'ml') return { kind: 'volume', amount, baseAmount: amount }
  return { kind: 'count', amount, baseAmount: amount }
}

function quantityForProduct(requested: RequestedQuantity, product: MerchantProduct): { quantity: number; error?: string } {
  if (requested.kind === 'count') return { quantity: requested.amount }
  const pack = product.name.match(/(\d+(?:\.\d+)?)\s*(kg|kgs|kilograms?|g|grams?|ml|l|litres?|liters?)\b/i)
  if (!pack) {
    if (Number.isInteger(requested.amount) && requested.amount > 0) return { quantity: requested.amount, error: 'Catalog pack size is unspecified; quantity uses the saved stock unit.' }
    return { quantity: 1, error: 'This weight or volume is not a whole saved stock unit. Select a matching pack size.' }
  }
  const packUnit = pack[2].toLowerCase()
  const packKind = ['kg', 'kgs', 'kilogram', 'kilograms', 'g', 'gram', 'grams'].includes(packUnit) ? 'mass' : 'volume'
  if (packKind !== requested.kind) return { quantity: 1, error: 'The spoken unit does not match this product pack.' }
  const packAmount = Number(pack[1])
  const packBaseAmount = packKind === 'mass'
    ? packAmount * (['kg', 'kgs', 'kilogram', 'kilograms'].includes(packUnit) ? 1000 : 1)
    : packAmount * (['l', 'litre', 'litres', 'liter', 'liters'].includes(packUnit) ? 1000 : 1)
  const quantity = requested.baseAmount / packBaseAmount
  if (!Number.isInteger(quantity) || quantity < 1) return { quantity: 1, error: 'The requested amount is not a whole number of this product pack.' }
  return { quantity }
}

function parseSpokenLines(transcript: string, products: MerchantProduct[]): BillingLine[] {
  const cleaned = transcript.replace(/\b(?:and then|then)\b/gi, ' and ').replace(/[.!?]+/g, ' ').trim()
  const quantityPattern = /(?:^|[\s,;])((?:half\s+(?:a\s+)?(?:kilos?|kilograms?|kgs?|kg))|(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|a|an)(?:\s+(?:kilos?|kilograms?|kgs?|kg|grams?|g|litres?|liters?|l|ml|packets?|packs?|bottles?|pieces?|pcs?))?)(?=\s|$)/gi
  const expressions = [...cleaned.matchAll(quantityPattern)].map((match) => {
    const expression = match[1].trim()
    const markerStart = (match.index ?? 0) + match[0].lastIndexOf(expression)
    return { expression, start: markerStart, end: markerStart + expression.length }
  })
  const segments: { expression?: string; productName: string }[] = []
  if (!expressions.length) {
    segments.push(...cleaned.split(/[,;\n]|\band\b/i).map((part) => ({ productName: part.trim() })).filter((part) => part.productName))
  } else {
    const leadingText = cleaned.slice(0, expressions[0].start).replace(/^[,;\s]+|[,;\s]+$/g, '').trim()
    if (leadingText) segments.push({ productName: leadingText })
    for (let index = 0; index < expressions.length; index += 1) {
      const current = expressions[index]
      const end = expressions[index + 1]?.start ?? cleaned.length
      const productName = cleaned.slice(current.end, end).replace(/^[,;\s]+|[,;\s]+$/g, '').replace(/^(?:of|and)\s+/i, '').replace(/\b(and|of)\b\s*$/i, '').trim()
      if (productName) segments.push({ expression: current.expression, productName })
    }
  }

  return segments.flatMap((segment) => {
    const requested = segment.expression ? parseRequestedQuantity(segment.expression) : { kind: 'count' as const, amount: 1, baseAmount: 1 }
    const phrases = segment.productName.split(/\s+and\s+/i).map((part) => part.trim()).filter(Boolean)
    const resolved = phrases.map((phrase) => {
      const matchedProduct = bestProductMatch(phrase, products, requested)
      const line = newLine(phrase)
      line.requested = requested
      if (!matchedProduct) return line
      const matchQuantity = quantityForProduct(requested, matchedProduct)
      if (matchQuantity.error && (!Number.isInteger(matchQuantity.quantity) || matchQuantity.quantity < 1)) return { ...line, matchError: matchQuantity.error }
      return { ...line, productId: matchedProduct.id, quantity: matchQuantity.quantity, matchError: matchQuantity.error }
    })
    return resolved.length > 1 && resolved.every((line) => !line.productId) ? [newLine(segment.productName)] : resolved
  })
}

const formatMoney = (amount: number) => `₹${amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export function TransactionForm({ products, onSave, isLoading = false }: TransactionFormProps) {
  const [mode, setMode] = useState<BillingMode>('manual')
  const [manualLines, setManualLines] = useState<BillingLine[]>([newLine()])
  const [voiceLines, setVoiceLines] = useState<BillingLine[]>([])
  const [transcript, setTranscript] = useState('')
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('UPI')
  const [customerReference, setCustomerReference] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  useEffect(() => () => recognitionRef.current?.stop(), [])

  function productFor(line: BillingLine) {
    return products.find((product) => product.id === line.productId)
  }

  const manualTotal = useMemo(
    () => manualLines.reduce((sum, line) => sum + (products.find((product) => product.id === line.productId)?.unitPrice ?? 0) * line.quantity, 0),
    [manualLines, products],
  )
  const voiceTotal = useMemo(
    () => voiceLines.reduce((sum, line) => sum + (products.find((product) => product.id === line.productId)?.unitPrice ?? 0) * line.quantity, 0),
    [voiceLines, products],
  )

  function updateManualLine(id: string, updates: Partial<BillingLine>) {
    setManualLines((current) => current.map((line) => line.id === id ? { ...line, ...updates } : line))
    setMessage(null)
  }

  function updateVoiceLine(id: string, updates: Partial<BillingLine>) {
    setVoiceLines((current) => current.map((line) => line.id === id ? { ...line, ...updates } : line))
    setMessage(null)
  }

  function selectVoiceProduct(line: BillingLine, productId: string) {
    const product = products.find((item) => item.id === productId)
    if (!product) {
      updateVoiceLine(line.id, { productId: '', matchError: undefined })
      return
    }
    const matchQuantity = line.requested ? quantityForProduct(line.requested, product) : { quantity: line.quantity }
    if (matchQuantity.error && (!Number.isInteger(matchQuantity.quantity) || matchQuantity.quantity < 1)) {
      updateVoiceLine(line.id, { productId: '', matchError: matchQuantity.error })
      return
    }
    updateVoiceLine(line.id, { productId, quantity: matchQuantity.quantity, matchError: matchQuantity.error })
  }

  function validateLines(lines: BillingLine[]): string | null {
    if (!lines.length) return 'Add at least one product to the bill.'
    const requiredStock = new Map<string, number>()
    for (const line of lines) {
      if (!line.productId) return line.spokenName ? `Select the correct product for “${line.spokenName}”.` : 'Choose a product for every bill line.'
      if (!Number.isInteger(line.quantity) || line.quantity < 1) return 'Quantities must be whole numbers greater than zero.'
      requiredStock.set(line.productId, (requiredStock.get(line.productId) ?? 0) + line.quantity)
    }
    for (const [productId, quantity] of requiredStock) {
      const product = products.find((item) => item.id === productId)
      if (!product) return 'A selected product is no longer available. Refresh the catalog and try again.'
      if (quantity > product.stockQuantity) return `Only ${product.stockQuantity} units of ${product.name} are currently in stock.`
    }
    return null
  }

  async function saveBill(lines: BillingLine[]): Promise<boolean> {
    const validationError = validateLines(lines)
    if (validationError) {
      setMessage({ type: 'error', text: validationError })
      return false
    }
    setIsSaving(true)
    setMessage(null)
    try {
      const transaction = await onSave({
        items: lines.map(({ productId, quantity }) => ({ productId, quantity })),
        paymentMethod,
        customerReference: customerReference.trim() || undefined,
      })
      setMessage({ type: 'success', text: `${transaction.id} recorded successfully.` })
      return true
    } catch (saveError) {
      setMessage({ type: 'error', text: saveError instanceof Error ? saveError.message : 'Could not record the transaction.' })
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function handleManualSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (await saveBill(manualLines)) {
      setManualLines([newLine()])
      setCustomerReference('')
      setPaymentMethod('UPI')
    }
  }

  function startVoiceCapture() {
    setMessage(null)
    setTranscript('')
    setVoiceLines([])
    const speechWindow = window as SpeechWindow
    const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition
    if (!Recognition) {
      setMessage({ type: 'error', text: 'Voice recognition is unavailable in this browser. Type the spoken items below and select Parse items.' })
      return
    }
    const recognition = new Recognition()
    recognition.lang = 'en-IN'
    recognition.continuous = false
    recognition.interimResults = true
    recognition.onresult = (event) => {
      const recognizedText = Array.from(event.results).map((result) => result[0]?.transcript ?? '').join(' ').trim()
      setTranscript(recognizedText)
      const finalText = Array.from(event.results).filter((result) => result.isFinal).map((result) => result[0]?.transcript ?? '').join(' ').trim()
      if (finalText) {
        setVoiceLines(parseSpokenLines(finalText, products))
      }
    }
    recognition.onerror = (event) => {
      setIsListening(false)
      setMessage({ type: 'error', text: event.error === 'not-allowed' ? 'Microphone permission was denied. Allow microphone access or type the items instead.' : `Voice capture failed (${event.error}). Try again or type the items.` })
    }
    recognition.onend = () => setIsListening(false)
    recognitionRef.current = recognition
    setIsListening(true)
    try {
      recognition.start()
    } catch {
      setIsListening(false)
      setMessage({ type: 'error', text: 'Could not start voice capture. Try again or type the items.' })
    }
  }

  function parseTranscript() {
    const parsed = parseSpokenLines(transcript, products)
    setVoiceLines(parsed)
    setMessage(parsed.length ? null : { type: 'error', text: 'No items were detected. Try a phrase such as “two kilos of toor dal”.' })
  }

  async function confirmVoiceSale() {
    if (await saveBill(voiceLines)) {
      setVoiceLines([])
      setTranscript('')
      setCustomerReference('')
      setPaymentMethod('UPI')
    }
  }

  return (
    <section className="panel transaction-form-panel" aria-labelledby="record-sale-title">
      <div className="panel-heading">
        <div>
          <h2 id="record-sale-title">Create a bill</h2>
          <p>Add one or more products to a single transaction</p>
        </div>
        <span className="form-heading-icon"><Plus size={17} /></span>
      </div>

      <div className="billing-mode-toggle" role="tablist" aria-label="Billing mode">
        <button type="button" role="tab" aria-selected={mode === 'manual'} className={mode === 'manual' ? 'active' : ''} onClick={() => { setMode('manual'); setMessage(null) }}>Manual Billing</button>
        <button type="button" role="tab" aria-selected={mode === 'voice'} className={mode === 'voice' ? 'active' : ''} onClick={() => { setMode('voice'); setMessage(null) }}>Voice Billing</button>
      </div>

      {mode === 'manual' ? <form className="transaction-form" onSubmit={handleManualSubmit} noValidate>
        <div className="bill-lines-heading"><span>Product</span><span>Qty</span><span>Unit price</span><span>Subtotal</span><span /></div>
        <div className="bill-line-list">
          {manualLines.map((line) => {
            const product = productFor(line)
            return <div className="bill-line-row" key={line.id}>
              <select aria-label="Product" value={line.productId} onChange={(event) => updateManualLine(line.id, { productId: event.target.value })} required>
                <option value="">Select product</option>
                {products.map((item) => <option key={item.id} value={item.id} disabled={item.stockQuantity === 0}>{item.name} · {item.sku}{item.stockQuantity === 0 ? ' · Out of stock' : ''}</option>)}
              </select>
              <input aria-label="Quantity" type="number" min="1" step="1" value={line.quantity || ''} onChange={(event) => updateManualLine(line.id, { quantity: Number(event.target.value) })} />
              <span className="bill-price">{product ? formatMoney(product.unitPrice) : '—'}</span>
              <strong className="bill-subtotal">{product && line.quantity > 0 ? formatMoney(product.unitPrice * line.quantity) : '—'}</strong>
              <button className="bill-remove-button" type="button" aria-label={`Remove ${product?.name ?? 'product'}`} onClick={() => setManualLines((current) => current.filter((item) => item.id !== line.id))}><Trash2 size={15} /></button>
            </div>
          })}
        </div>
        <button className="bill-add-line" type="button" onClick={() => setManualLines((current) => current.length < 50 ? [...current, newLine()] : current)} disabled={manualLines.length >= 50}><Plus size={15} />Add Product</button>

        <div className="billing-details-grid">
          <label className="form-field"><span>Payment method</span><select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as PaymentMethod)}>{paymentMethods.map((method) => <option key={method} value={method}>{method}</option>)}</select></label>
          <label className="form-field"><span>Customer reference <small>(optional)</small></span><input type="text" maxLength={100} value={customerReference} onChange={(event) => setCustomerReference(event.target.value)} placeholder="Loyalty ID or customer code" /></label>
        </div>

        <div className="transaction-total"><span>Total amount</span><strong>{formatMoney(manualTotal)}</strong></div>
        {message && <div className={`form-message ${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>{message.type === 'success' ? <Check size={15} /> : <CircleAlert size={15} />}<span>{message.text}</span></div>}
        <button className="submit-transaction" type="submit" disabled={isSaving || isLoading}><Plus size={16} />{isSaving ? 'Recording…' : 'Record transaction'}</button>
      </form> : <div className="voice-billing-panel">
        <div className={`voice-recorder ${isListening ? 'recording' : ''}`}>
          <button className="voice-record-button" type="button" onClick={() => isListening ? recognitionRef.current?.stop() : startVoiceCapture()} disabled={isSaving || isLoading} aria-label={isListening ? 'Stop voice recording' : 'Start voice recording'}>
            {isListening ? <MicOff size={19} /> : <Mic size={19} />}
          </button>
          <div><strong>{isListening ? 'Listening…' : 'Speak your grocery items'}</strong><span>{isListening ? 'Say each quantity and product, then stop.' : 'Example: “Two kilos of toor dal, one masala packet, and two biscuits.”'}</span><small>Separate multiple items with commas or 'and'.</small></div>
          {isListening && <span className="voice-live-indicator"><i /><i /><i /></span>}
        </div>
        <label className="form-field voice-transcript-field"><span>Recognized text <small>(edit if needed)</small></span><textarea rows={1} value={transcript} onChange={(event) => { setTranscript(event.target.value); setVoiceLines([]) }} placeholder="Your spoken items will appear here. You can also type them." /></label>
        <button className="bill-add-line" type="button" onClick={parseTranscript} disabled={!transcript.trim() || isListening}><Check size={15} />Parse items</button>

        {voiceLines.length > 0 && <>
          <div className="bill-lines-heading voice-bill-heading"><span>Detected item</span><span>Qty</span><span>Unit price</span><span>Subtotal</span><span /></div>
          <div className="bill-line-list">
            {voiceLines.map((line) => {
              const product = productFor(line)
              return <div className={`bill-line-row ${!line.productId ? 'needs-match' : ''}`} key={line.id}>
                <div className="voice-product-choice">
                  {line.spokenName && !line.productId && <small>“{line.spokenName}”</small>}
                  <select aria-label={`Correct product for ${line.spokenName || 'spoken item'}`} value={line.productId} onChange={(event) => selectVoiceProduct(line, event.target.value)}>
                    <option value="">{line.productId ? 'Select product' : 'Choose the correct product'}</option>
                    {products.map((item) => <option key={item.id} value={item.id} disabled={item.stockQuantity === 0}>{item.name} · {item.sku}</option>)}
                  </select>
                  {!line.productId && <em>{line.matchError ?? 'Product not confidently matched — please select the correct product.'}</em>}
                  {line.productId && line.matchError && <em>{line.matchError}</em>}
                </div>
                <input aria-label="Quantity" type="number" min="1" step="1" value={line.quantity || ''} onChange={(event) => updateVoiceLine(line.id, { quantity: Number(event.target.value) })} />
                <span className="bill-price">{product ? formatMoney(product.unitPrice) : '—'}</span>
                <strong className="bill-subtotal">{product && line.quantity > 0 ? formatMoney(product.unitPrice * line.quantity) : '—'}</strong>
                <button className="bill-remove-button" type="button" aria-label={`Remove ${product?.name ?? line.spokenName}`} onClick={() => setVoiceLines((current) => current.filter((item) => item.id !== line.id))}><Trash2 size={15} /></button>
              </div>
            })}
          </div>
          <button className="bill-add-line" type="button" onClick={() => setVoiceLines((current) => current.length < 50 ? [...current, newLine()] : current)} disabled={voiceLines.length >= 50}><Plus size={15} />Add Product</button>
          <div className="billing-details-grid">
            <label className="form-field"><span>Payment method</span><select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as PaymentMethod)}>{paymentMethods.map((method) => <option key={method} value={method}>{method}</option>)}</select></label>
            <label className="form-field"><span>Customer reference <small>(optional)</small></span><input type="text" maxLength={100} value={customerReference} onChange={(event) => setCustomerReference(event.target.value)} placeholder="Loyalty ID or customer code" /></label>
          </div>
          <div className="transaction-total"><span>Total amount</span><strong>{formatMoney(voiceTotal)}</strong></div>
          <button className="submit-transaction" type="button" disabled={isSaving || isLoading || isListening} onClick={confirmVoiceSale}><Check size={16} />{isSaving ? 'Recording…' : 'Review and confirm'}</button>
        </>}
        {message && <div className={`form-message ${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>{message.type === 'success' ? <Check size={15} /> : <CircleAlert size={15} />}<span>{message.text}</span></div>}
      </div>}
    </section>
  )
}
