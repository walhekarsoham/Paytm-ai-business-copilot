import type { AnalyticsPeriod, Campaign, DashboardSnapshot, MerchantProduct, MerchantSession, PaymentMethod, SaleInput, StockMovement, Transaction } from '../types/merchant'
export type { SaleInput } from '../types/merchant'

type DecimalValue = number | string

type MerchantResponse = {
  id: string
  businessName: string
  email: string
  createdAt: string
}

type AuthResponse = {
  accessToken: string
  tokenType: string
  merchant: MerchantResponse
}

type ProductResponse = Omit<MerchantProduct, 'unitPrice' | 'costPrice'> & {
  unitPrice: DecimalValue
  costPrice: DecimalValue
}

type TransactionItemResponse = {
  productId: string | null
  productName: string
  sku: string
  quantity: number
  unitPrice: DecimalValue
  lineTotal: DecimalValue
}

type TransactionResponse = {
  id: string
  total: DecimalValue
  paymentMethod: PaymentMethod
  customerReference: string | null
  createdAt: string
  items: TransactionItemResponse[]
}

type MovementResponse = {
  id: string
  productId: string | null
  productName: string
  movementType: string
  quantity: number
  reason: string
  createdAt: string
}

type InventoryResponse = { products: ProductResponse[]; movements: MovementResponse[] }
type CampaignResponse = Omit<Campaign, 'tone'> & { startsAt: string | null; createdAt: string }
type DashboardResponse = {
  period: AnalyticsPeriod
  totalSales: DecimalValue
  totalOrders: number
  customers: number
  averageOrderValue: DecimalValue
  salesChangePercent: DecimalValue | null
  salesSeries: { label: string; current: DecimalValue; previous: DecimalValue }[]
  topProducts: { name: string; category: string; sold: number; revenue: DecimalValue; share: number; tone: string; initials: string }[]
  inventoryAlerts: { name: string; sku: string; stock: number; status: string; tone: string }[]
  insights: { title: string; description: string; tag: string; tone: string }[]
}

export type CopilotMetric = { key: string; label: string; value: number | string; unit: string | null }
export type CopilotSeverity = 'info' | 'opportunity' | 'warning' | 'critical'
export type CopilotInsight = { title: string; explanation: string; supportingMetrics: CopilotMetric[]; severity: Exclude<CopilotSeverity, 'critical'> }
export type BusinessOpportunity = {
  type: string
  severity: CopilotSeverity
  title: string
  reason: string
  metrics: Record<string, number | string>
  recommendedAction: string
}
export type CopilotRecommendation = {
  title: string
  opportunityType: string | null
  whatIsHappening: string
  whyItMatters: string
  reason: string
  explanation?: string | null
  supportingMetrics: CopilotMetric[]
  supportingNumbers: Record<string, number | string>
  metrics?: Record<string, number | string>
  recommendedAction: string
  expectedImpact: string
  confidence: number
  actionType: 'RESTOCK_PRODUCT' | 'CREATE_PROMOTION' | 'CREATE_BUNDLE' | 'REVIEW_SALES'
  action?: string | null
  requiresApproval: boolean
  requiresConfirmation: boolean
}
export type CopilotRecommendationsResponse = {
  merchantName: string
  recommendations: CopilotRecommendation[]
  generatedAt: string
}
export type CopilotChatMessage = { role: 'merchant' | 'ai'; content: string }
export type CopilotChatResponse = {
  answer: string
  supportingMetrics: CopilotMetric[]
  insufficientData: boolean
  generatedAt: string
}
export type CopilotAnalysis = {
  merchantName: string
  provider: string
  summary: string
  insights: CopilotInsight[]
  opportunities: BusinessOpportunity[]
  recommendedActions: CopilotRecommendation[]
  generatedAt: string
}

export type AuthInput = { email: string; password: string; businessName?: string }

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const tokenKey = 'paytm-merchant-access-token'
let accessToken: string | null = typeof window === 'undefined' ? null : window.sessionStorage.getItem(tokenKey)

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

export function setAccessToken(token: string | null) {
  accessToken = token
  if (typeof window === 'undefined') return
  if (token) window.sessionStorage.setItem(tokenKey, token)
  else window.sessionStorage.removeItem(tokenKey)
}

export function getAccessToken() {
  return accessToken
}

function errorMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const firstError = detail[0] as { msg?: string } | undefined
    if (firstError?.msg) return firstError.msg
  }
  return 'The request could not be completed. Please try again.'
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers })
  } catch {
    throw new ApiError('Could not reach the API. Check that the backend is running and try again.', 0)
  }
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null) as { detail?: unknown } | null
  if (!response.ok) {
    if (response.status === 401) setAccessToken(null)
    throw new ApiError(errorMessage(body?.detail), response.status)
  }
  return body as T
}

function mapMerchant(merchant: MerchantResponse): MerchantSession {
  return { id: merchant.id, businessName: merchant.businessName, email: merchant.email, createdAt: merchant.createdAt }
}

function mapProduct(product: ProductResponse): MerchantProduct {
  return { ...product, unitPrice: Number(product.unitPrice), costPrice: Number(product.costPrice) }
}

function mapTransaction(transaction: TransactionResponse): Transaction {
  const firstItem = transaction.items[0]
  const itemCount = transaction.items.length
  return {
    id: transaction.id,
    productId: firstItem?.productId ?? '',
    productName: itemCount > 1 ? `${firstItem?.productName ?? 'Sale'} + ${itemCount - 1} more` : firstItem?.productName ?? 'Removed product',
    sku: firstItem?.sku ?? '',
    searchText: transaction.items.map((item) => `${item.productName} ${item.sku}`).join(' '),
    quantity: transaction.items.reduce((total, item) => total + item.quantity, 0),
    unitPrice: Number(firstItem?.unitPrice ?? 0),
    total: Number(transaction.total),
    paymentMethod: transaction.paymentMethod,
    date: transaction.createdAt,
  }
}

function mapMovement(movement: MovementResponse): StockMovement {
  const movementType = ['opening', 'restock', 'adjustment', 'sale'].includes(movement.movementType)
    ? movement.movementType as StockMovement['type']
    : 'adjustment'
  return {
    id: movement.id,
    productId: movement.productId ?? '',
    productName: movement.productName,
    date: movement.createdAt,
    quantity: movement.quantity,
    type: movementType,
    reason: movement.reason,
  }
}

export const api = {
  auth: {
    async register(input: AuthInput) {
      const result = await request<AuthResponse>('/auth/register', { method: 'POST', body: JSON.stringify(input) })
      setAccessToken(result.accessToken)
      return mapMerchant(result.merchant)
    },
    async login(input: AuthInput) {
      const result = await request<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify(input) })
      setAccessToken(result.accessToken)
      return mapMerchant(result.merchant)
    },
    async me() {
      const merchant = await request<MerchantResponse>('/auth/me')
      return mapMerchant(merchant)
    },
    logout() {
      setAccessToken(null)
    },
  },
  dashboard: {
    async get(period: AnalyticsPeriod = '7d'): Promise<DashboardSnapshot> {
      const result = await request<DashboardResponse>(`/dashboard?period=${period}`)
      return {
        period: result.period,
        totalSales: Number(result.totalSales),
        totalOrders: result.totalOrders,
        customers: result.customers,
        averageOrderValue: Number(result.averageOrderValue),
        salesChangePercent: result.salesChangePercent === null ? null : Number(result.salesChangePercent),
        salesSeries: result.salesSeries.map((point) => ({ ...point, current: Number(point.current), previous: Number(point.previous) })),
        topProducts: result.topProducts.map((product) => ({ ...product, revenue: Number(product.revenue) })),
        inventoryAlerts: result.inventoryAlerts,
        insights: result.insights,
      }
    },
  },
  products: {
    async list() {
      return (await request<ProductResponse[]>('/products')).map(mapProduct)
    },
    async create(product: MerchantProduct) {
      const { id: _id, ...payload } = product
      return mapProduct(await request<ProductResponse>('/products', { method: 'POST', body: JSON.stringify(payload) }))
    },
    async update(product: MerchantProduct) {
      const { id, ...payload } = product
      return mapProduct(await request<ProductResponse>(`/products/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(payload) }))
    },
    async delete(productId: string) {
      await request<void>(`/products/${encodeURIComponent(productId)}`, { method: 'DELETE' })
    },
  },
  transactions: {
    async list() {
      return (await request<TransactionResponse[]>('/transactions')).map(mapTransaction)
    },
    async listToday() {
      return (await request<TransactionResponse[]>('/transactions?today=true&limit=1000')).map(mapTransaction)
    },
    async create(sale: SaleInput) {
      const result = await request<TransactionResponse>('/transactions', {
        method: 'POST',
        body: JSON.stringify({
          items: sale.items,
          paymentMethod: sale.paymentMethod,
          customerReference: sale.customerReference || null,
        }),
      })
      return mapTransaction(result)
    },
  },
  inventory: {
    async get() {
      const result = await request<InventoryResponse>('/inventory')
      return { products: result.products.map(mapProduct), movements: result.movements.map(mapMovement) }
    },
    async restock(productId: string, quantity: number, reason: string) {
      return mapProduct(await request<ProductResponse>(`/inventory/products/${encodeURIComponent(productId)}/restock`, {
        method: 'POST', body: JSON.stringify({ quantity, reason }),
      }))
    },
    async setCount(productId: string, stockQuantity: number, reason: string) {
      return mapProduct(await request<ProductResponse>(`/inventory/products/${encodeURIComponent(productId)}/count`, {
        method: 'POST', body: JSON.stringify({ stockQuantity, reason }),
      }))
    },
    async updateThreshold(productId: string, lowStockThreshold: number) {
      return mapProduct(await request<ProductResponse>(`/inventory/products/${encodeURIComponent(productId)}/threshold`, {
        method: 'PATCH', body: JSON.stringify({ lowStockThreshold }),
      }))
    },
  },
  campaigns: {
    async list() {
      const campaigns = await request<CampaignResponse[]>('/campaigns')
      return campaigns.map((campaign, index): Campaign => ({ ...campaign, tone: ['mint', 'lavender', 'peach', 'blue'][index % 4] }))
    },
  },
  aiCopilot: {
    async analyze(question?: string) {
      return request<CopilotAnalysis>('/ai-copilot/analyze', {
        method: 'POST',
        body: JSON.stringify({ question: question?.trim() || null }),
      })
    },
    async recommendations() {
      return request<CopilotRecommendationsResponse>('/ai-copilot/recommendations')
    },
    async chat(message: string, conversation: CopilotChatMessage[] = []) {
      return request<CopilotChatResponse>('/ai-copilot/chat', {
        method: 'POST',
        body: JSON.stringify({ message, conversation }),
      })
    },
  },
}
