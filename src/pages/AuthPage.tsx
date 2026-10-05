import { useState, type FormEvent } from 'react'
import { ArrowRight, LoaderCircle, ShieldCheck } from 'lucide-react'
import type { AuthInput } from '../lib/apiClient'

type AuthMode = 'login' | 'register'

type AuthPageProps = {
  error: string | null
  onAuthenticate: (input: AuthInput, mode: AuthMode) => Promise<void>
}

export function AuthPage({ error, onAuthenticate }: AuthPageProps) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [businessName, setBusinessName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    if (mode === 'register' && businessName.trim().length < 2) {
      setFormError('Enter your grocery business name.')
      return
    }
    if (password.length < 8) {
      setFormError('Password must contain at least 8 characters.')
      return
    }
    setIsSubmitting(true)
    try {
      await onAuthenticate({ email: email.trim(), password, ...(mode === 'register' ? { businessName: businessName.trim() } : {}) }, mode)
    } catch (submitError) {
      setFormError(submitError instanceof Error ? submitError.message : 'Authentication failed. Try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-screen">
      <div className="auth-sideband">
        <a className="brand auth-brand" href="#login" aria-label="Paytm for Business">
          <img className="brand-logo" src="/paytm-business-logo.svg" alt="Paytm for Business" />
        </a>
        <div className="auth-sideband-copy"><span className="auth-kicker">PAYTM FOR BUSINESS</span><h1>Everyday grocery trade, made clearer.</h1><p>Sales, products and stock for your grocery business, together in one workspace.</p></div>
        <div className="auth-sideband-footer"><ShieldCheck size={15} /><span>Your merchant data is protected by account-based access.</span></div>
      </div>
      <section className="auth-main" aria-labelledby="auth-title">
        <div className="auth-card">
          <span className="auth-kicker">MERCHANT WORKSPACE</span>
          <h2 id="auth-title">{mode === 'login' ? 'Welcome back' : 'Create your merchant account'}</h2>
          <p className="auth-subtitle">{mode === 'login' ? 'Sign in to manage your grocery business.' : 'Set up a secure account for your grocery business.'}</p>
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            {mode === 'register' && <label className="auth-field"><span>Business name</span><input autoComplete="organization" value={businessName} onChange={(event) => setBusinessName(event.target.value)} placeholder="Mehta Fresh Mart" required /></label>}
            <label className="auth-field"><span>Email address</span><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@yourstore.com" required /></label>
            <label className="auth-field"><span>Password</span><input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" minLength={8} required /></label>
            {(formError || error) && <p className="auth-error" role="alert">{formError ?? error}</p>}
            <button className="auth-submit" type="submit" disabled={isSubmitting}>{isSubmitting ? <LoaderCircle className="auth-spinner" size={16} /> : <ArrowRight size={16} />}{isSubmitting ? 'Connecting…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
          </form>
          <p className="auth-mode-switch">{mode === 'login' ? 'New to Paytm for Business?' : 'Already registered?'} <button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setFormError(null) }}>{mode === 'login' ? 'Create account' : 'Sign in'}</button></p>
        </div>
      </section>
    </main>
  )
}
