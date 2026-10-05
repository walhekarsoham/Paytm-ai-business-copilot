export type AppPage = 'Overview' | 'Sales' | 'Products' | 'Inventory' | 'AI Copilot' | 'Campaigns' | 'Settings'

export type PaymentMethod = 'UPI' | 'Cash' | 'Card' | 'Net banking'
export type AnalyticsPeriod = '7d' | '30d' | '12m'

export type MerchantSession = {
  id: string
  businessName: string
  email: string
  createdAt: string
}

export type Campaign = {
  id?: string
  name: string
  channel: string
  status: string
  reach: string
  tone: string
  startsAt?: string | null
  createdAt?: string
}

export type DashboardSnapshot = {
  period: AnalyticsPeriod
  totalSales: number
  totalOrders: number
  customers: number
  averageOrderValue: number
  salesChangePercent: number | null
  salesSeries: { label: string; current: number; previous: number }[]
  topProducts: { name: string; category: string; sold: number; revenue: number; share: number; tone: string; initials: string }[]
  inventoryAlerts: { name: string; sku: string; stock: number; status: string; tone: string }[]
  insights: { title: string; description: string; tag: string; tone: string }[]
}

export type MerchantProduct = {
  id: string
  name: string
  sku: string
  unitPrice: number
  category: string
  costPrice: number
  stockQuantity: number
  lowStockThreshold: number
}

export type StockMovement = {
  id: string
  productId: string
  productName: string
  date: string
  quantity: number
  type: 'opening' | 'restock' | 'adjustment' | 'sale'
  reason: string
}

export type Transaction = {
  id: string
  productId: string
  productName: string
  sku: string
  searchText?: string
  quantity: number
  unitPrice: number
  total: number
  paymentMethod: PaymentMethod
  date: string
  customerReference?: string | null
}

export type SaleItemInput = {
  productId: string
  quantity: number
}

export type SaleInput = {
  items: SaleItemInput[]
  paymentMethod: PaymentMethod
  customerReference?: string
}
