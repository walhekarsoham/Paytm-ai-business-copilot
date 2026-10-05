import { useEffect, useState } from 'react'
import { api, ApiError, getAccessToken, type AuthInput, type SaleInput } from './lib/apiClient'
import type { AnalyticsPeriod, AppPage, Campaign, DashboardSnapshot, MerchantProduct, MerchantSession, StockMovement, Transaction } from './types/merchant'
import { DashboardLayout } from './components/layout/DashboardLayout'
import { Dashboard } from './pages/Dashboard'
import { Sales } from './pages/Sales'
import { WorkspacePage } from './pages/WorkspacePage'
import { AuthPage } from './pages/AuthPage'

export function App() {
  const [activePage, setActivePage] = useState<AppPage>('Overview')
  const [dashboardPeriod, setDashboardPeriod] = useState<AnalyticsPeriod>('7d')
  const [merchant, setMerchant] = useState<MerchantSession | null>(null)
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null)
  const [products, setProducts] = useState<MerchantProduct[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [todayTransactions, setTodayTransactions] = useState<Transaction[]>([])
  const [stockMovements, setStockMovements] = useState<StockMovement[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [isCheckingSession, setIsCheckingSession] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [isDashboardLoading, setIsDashboardLoading] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)

  async function refreshWorkspace() {
    setIsLoading(true)
    setPageError(null)
    try {
      const [dashboardData, productData, transactionData, todayTransactionData, inventoryData, campaignData] = await Promise.all([
        api.dashboard.get(dashboardPeriod),
        api.products.list(),
        api.transactions.list(),
        api.transactions.listToday(),
        api.inventory.get(),
        api.campaigns.list(),
      ])
      setDashboard(dashboardData)
      setProducts(productData)
      setTransactions(transactionData)
      setTodayTransactions(todayTransactionData)
      setStockMovements(inventoryData.movements)
      setCampaigns(campaignData)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      setIsCheckingSession(false)
      return
    }
    void (async () => {
      try {
        setMerchant(await api.auth.me())
        await refreshWorkspace()
      } catch (error) {
        api.auth.logout()
        setMerchant(null)
        setAuthError(error instanceof Error ? error.message : 'Could not restore your session.')
      } finally {
        setIsCheckingSession(false)
      }
    })()
  }, [])

  async function authenticate(input: AuthInput, mode: 'login' | 'register') {
    setAuthError(null)
    const session = mode === 'register' ? await api.auth.register(input) : await api.auth.login(input)
    setMerchant(session)
    try {
      await refreshWorkspace()
    } catch (error) {
      api.auth.logout()
      setMerchant(null)
      throw error
    }
  }

  async function changeDashboardPeriod(period: AnalyticsPeriod) {
    if (period === dashboardPeriod) return
    setDashboardPeriod(period)
    setDashboard(null)
    setIsDashboardLoading(true)
    setPageError(null)
    try {
      setDashboard(await api.dashboard.get(period))
    } catch (error) {
      handlePageError(error)
    } finally {
      setIsDashboardLoading(false)
    }
  }

  function handlePageError(error: unknown) {
    if (error instanceof ApiError && error.status === 401) {
      api.auth.logout()
      setMerchant(null)
      setAuthError('Your session has expired. Sign in again to continue.')
    }
    setPageError(error instanceof Error ? error.message : 'The request could not be completed.')
  }

  async function addTransaction(sale: SaleInput) {
    setPageError(null)
    try {
      const transaction = await api.transactions.create(sale)
      await refreshWorkspace()
      return transaction
    } catch (error) {
      handlePageError(error)
      throw error
    }
  }

  async function saveProduct(product: MerchantProduct) {
    setPageError(null)
    try {
      if (products.some((current) => current.id === product.id)) await api.products.update(product)
      else await api.products.create(product)
      await refreshWorkspace()
    } catch (error) {
      handlePageError(error)
      throw error
    }
  }

  async function deleteProduct(productId: string) {
    setPageError(null)
    try {
      await api.products.delete(productId)
      await refreshWorkspace()
    } catch (error) {
      handlePageError(error)
      throw error
    }
  }

  async function restockProduct(productId: string, quantity: number, reason: string) {
    setPageError(null)
    try {
      await api.inventory.restock(productId, quantity, reason)
      await refreshWorkspace()
    } catch (error) {
      handlePageError(error)
      throw error
    }
  }

  async function setProductStock(productId: string, quantity: number, reason: string) {
    setPageError(null)
    try {
      await api.inventory.setCount(productId, quantity, reason)
      await refreshWorkspace()
    } catch (error) {
      handlePageError(error)
      throw error
    }
  }

  async function updateLowStockThreshold(productId: string, threshold: number) {
    setPageError(null)
    try {
      await api.inventory.updateThreshold(productId, threshold)
      await refreshWorkspace()
    } catch (error) {
      handlePageError(error)
      throw error
    }
  }

  function logout() {
    api.auth.logout()
    setMerchant(null)
    setDashboard(null)
    setProducts([])
    setTransactions([])
    setTodayTransactions([])
    setStockMovements([])
    setCampaigns([])
    setPageError(null)
  }

  if (isCheckingSession) return <div className="app-loading-state"><span className="auth-spinner"><span /></span><p>Checking your merchant session…</p></div>
  if (!merchant) return <AuthPage error={authError} onAuthenticate={authenticate} />

  const page = activePage === 'Overview'
    ? <Dashboard data={dashboard} period={dashboardPeriod} isLoading={isLoading || isDashboardLoading} error={pageError} onPeriodChange={changeDashboardPeriod} />
    : activePage === 'Sales'
      ? <Sales transactions={todayTransactions} products={products} onAddTransaction={addTransaction} isLoading={isLoading} error={pageError} />
      : <WorkspacePage
          page={activePage}
          products={products}
          transactions={transactions}
          movements={stockMovements}
          campaigns={campaigns}
          dashboard={dashboard}
          merchant={merchant}
          isLoading={isLoading}
          error={pageError}
          onSaveProduct={saveProduct}
          onDeleteProduct={deleteProduct}
          onRestock={restockProduct}
          onSetStock={setProductStock}
          onUpdateThreshold={updateLowStockThreshold}
        />

  return (
    <DashboardLayout activePage={activePage} onNavigate={setActivePage} merchant={merchant} onLogout={logout}>
      {page}
    </DashboardLayout>
  )
}
