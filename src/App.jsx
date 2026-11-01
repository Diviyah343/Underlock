import { useEffect, useRef, useState } from 'react'
import { Eye, EyeOff, LockKeyhole, UserRound } from 'lucide-react'
import TransactionsPage from './Transactions.jsx'
import InvestigationsPage from './Investigations.jsx'
import LinkedAccountsPage from './LinkedAccounts.jsx'
import SettingsPage from './Settings.jsx'
import { getAccessToken, getAnalystId, login } from './api/client.js'
import { getAlert, getAlerts, submitAlertDecision } from './api/alerts.js'
import { openEventStream } from './api/sse.js'

const defaultAnalyst = 'AN-8902'

function WeightBar({ percent }) {
  const safePercent = Math.min(100, Math.max(0, Number(percent) || 0))

  return (
    <div className="mt-[8px] h-[4px] w-full overflow-hidden rounded-[2px] bg-[#e0e0e0]">
      <div className="h-full rounded-[2px] bg-[#1a1a1a]" style={{ width: `${safePercent}%` }} />
    </div>
  )
}

function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-GB', { timeZone: 'UTC' })
}

function formatDuration(seconds) {
  const safeSeconds = Math.max(0, Number(seconds) || 0)
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const remainder = safeSeconds % 60
  return hours > 0
    ? `${hours}h ${minutes}m ${remainder}s`
    : `${minutes}m ${remainder}s`
}

function formatMoney(amount, currency = 'USD') {
  const value = Number(amount)
  if (!Number.isFinite(value)) return `${amount ?? '—'} ${currency}`
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(value)
}

function AlertQueue({ analystId, onNavigate }) {
  const [alerts, setAlerts] = useState([])
  const [selectedAlertId, setSelectedAlertId] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const decidedAlertIds = useRef(new Set())

  useEffect(() => {
    let active = true
    const controller = new AbortController()

    async function refreshAlerts() {
      const result = await getAlerts({ status: 'open', page: 1, pageSize: 100 }, {
        signal: controller.signal,
      })
      if (active) {
        setAlerts(result.items.filter((alert) => !decidedAlertIds.current.has(alert.id)))
        setError('')
        setIsLoading(false)
      }
    }

    void refreshAlerts().catch((loadError) => {
      if (active && loadError.name !== 'AbortError') {
        setError(loadError.message || 'Unable to load alerts.')
        setIsLoading(false)
      }
    })

    const stream = openEventStream('/alerts/stream', {
      onEvent(event) {
        if (event.event !== 'alert') return
        void refreshAlerts().catch((loadError) => {
          if (active && loadError.name !== 'AbortError') {
            setError(loadError.message || 'Unable to refresh alerts.')
          }
        })
      },
      onError(streamError) {
        if (active) setError(streamError.message || 'Alert stream disconnected.')
      },
      signal: controller.signal,
    })

    return () => {
      active = false
      stream.close()
      controller.abort()
    }
  }, [])

  function handleDecisionComplete(alertId) {
    decidedAlertIds.current.add(alertId)
    setAlerts((currentAlerts) => currentAlerts.filter((alert) => alert.id !== alertId))
    setSelectedAlertId(null)
  }

  if (selectedAlertId) {
    return (
      <AlertDetail
        analystId={analystId}
        alertId={selectedAlertId}
        onBack={() => setSelectedAlertId(null)}
        onDecisionComplete={handleDecisionComplete}
        onNavigate={onNavigate}
      />
    )
  }

  return (
    <main className="app-shell">
      <Sidebar activeItem="Alert Queue" analystId={analystId} onNavigate={onNavigate} />
      <section className="app-content" aria-label="Alert queue workspace">
        <div className="min-h-full bg-[#f7f8f7]">
          <header className="flex items-center justify-between border-b border-[#dfe5e3] bg-[#fdfdfd] px-[22px] py-[14px]">
            <div>
              <h1 className="text-[15px] font-semibold text-[#1d2a29]">Alert Queue</h1>
              <p className="mt-[4px] font-mono text-[8px] text-[#63726f]">
                {alerts.length} open alerts · ordered by risk
              </p>
            </div>
          </header>
          {error && (
            <p className="border-b border-[#efb4ae] bg-[#f9d8d4] px-[22px] py-[9px] font-mono text-[9px] text-[#704e4a]" role="alert">
              {error}
            </p>
          )}
          <div className="space-y-[8px] p-[16px]">
            {isLoading && (
              <p className="border border-[#dfe5e3] bg-[#fdfdfd] px-[14px] py-[12px] font-mono text-[9px] text-[#63726f]">
                Loading alerts…
              </p>
            )}
            {!isLoading && alerts.length === 0 && !error && (
              <p className="border border-[#dfe5e3] bg-[#fdfdfd] px-[14px] py-[12px] font-mono text-[9px] text-[#63726f]">
                No open alerts.
              </p>
            )}
            {alerts.map((alert) => (
              <button
                key={alert.id}
                type="button"
                onClick={() => setSelectedAlertId(alert.id)}
                className="grid w-full grid-cols-[1fr_auto] items-center gap-[12px] border border-[#dfe5e3] bg-[#fdfdfd] px-[14px] py-[12px] text-left hover:bg-[#f6f8f7]"
              >
                <span className="min-w-0">
                  <span className="block truncate text-[10px] font-semibold text-[#1d2a29]">
                    {alert.priority || alert.rule_key || alert.id}
                  </span>
                  <span className="mt-[4px] block truncate font-mono text-[8px] text-[#63726f]">
                    {alert.incident_ref || alert.transaction_id} · {alert.tier || alert.severity} · {formatDateTime(alert.opened_at)}
                  </span>
                </span>
                <span className="font-mono text-[10px] font-semibold text-[#334340]">
                  {alert.risk_score}
                </span>
              </button>
            ))}
          </div>
        </div>
      </section>
    </main>
  )
}

function Sidebar({ activeItem, analystId, onNavigate }) {
  const navItems = ['Alert Queue', 'Investigations', 'Transactions', 'Settings']
  const destinations = {
    'Alert Queue': 'alert',
    Investigations: 'investigations',
    Transactions: 'transactions',
    Settings: 'settings',
  }

  return (
    <aside className="app-sidebar">
      <header className="app-sidebar-brand">Underlock</header>
      <nav className="app-sidebar-nav" aria-label="Primary navigation">
        {navItems.map((item) => (
          <button
            key={item}
            type="button"
            aria-current={item === activeItem ? 'page' : undefined}
            className={`app-sidebar-link ${item === activeItem ? 'is-active' : ''}`}
            onClick={() => onNavigate(destinations[item])}
          >
            {item}
          </button>
        ))}
      </nav>
      <footer className="app-sidebar-footer">
        <div className="app-sidebar-user">
          <span className="app-sidebar-avatar"><UserRound size={16} strokeWidth={1.8} aria-hidden="true" /></span>
          <span>Analyst: <strong>{analystId}</strong></span>
        </div>
        <div className="app-sidebar-status">
          <span className="app-sidebar-node"><span aria-hidden="true" />NODE_04: LIVE</span>
          <span>Latency: <strong>14ms</strong></span>
        </div>
      </footer>
    </aside>
  )
}

function SignedInLayout({ activeItem, analystId, onNavigate, children }) {
  return (
    <main className="app-shell">
      <Sidebar activeItem={activeItem} analystId={analystId} onNavigate={onNavigate} />
      <section className="app-content" aria-label={`${activeItem} workspace`}>
        {children}
      </section>
    </main>
  )
}

function AlertDetail({ analystId, alertId, onBack, onDecisionComplete, onNavigate }) {
  const [alert, setAlert] = useState(null)
  const [slaRemainingSeconds, setSlaRemainingSeconds] = useState(0)
  const [note, setNote] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setIsLoading(true)
    setError('')
    getAlert(alertId, { signal: controller.signal })
      .then((result) => {
        if (!active) return
        setAlert(result)
        setSlaRemainingSeconds(result.sla_remaining_seconds)
      })
      .catch((loadError) => {
        if (active && loadError.name !== 'AbortError') {
          setError(loadError.message || 'Unable to load alert details.')
        }
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [alertId])

  useEffect(() => {
    if (slaRemainingSeconds <= 0) return undefined
    const timer = window.setInterval(() => {
      setSlaRemainingSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [alert?.id, slaRemainingSeconds > 0])

  async function handleDecision(decision) {
    if (isSubmitting) return
    setIsSubmitting(true)
    setError('')
    try {
      await submitAlertDecision(alertId, decision, note)
      onDecisionComplete(alertId)
    } catch (decisionError) {
      setError(decisionError.message || 'Unable to submit the alert decision.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading && !alert) {
    return (
      <main className="app-shell">
        <Sidebar activeItem="Alert Queue" analystId={analystId} onNavigate={onNavigate} />
        <section className="app-content p-[22px]" aria-label="Alert detail workspace">
          <p className="font-mono text-[9px] text-[#63726f]">Loading alert details…</p>
        </section>
      </main>
    )
  }

  if (!alert) {
    return (
      <main className="app-shell">
        <Sidebar activeItem="Alert Queue" analystId={analystId} onNavigate={onNavigate} />
        <section className="app-content p-[22px]" aria-label="Alert detail workspace">
          <button type="button" onClick={onBack} className="font-mono text-[9px] text-[#334340]">
            ← Back to alert queue
          </button>
          {error && <p className="mt-[12px] font-mono text-[9px] text-[#9b3f3f]" role="alert">{error}</p>}
        </section>
      </main>
    )
  }

  const triggerTransaction = alert.trigger_transaction
  const flaggedAccount = alert.flagged_account
  const accountRows = [
    ['Location / IP', triggerTransaction?.jurisdiction || '—'],
    ['Device signature', '—'],
    ['Origin channel', '—'],
    ['Beneficiary entity', triggerTransaction?.beneficiary_id || '—'],
    ['Beneficiary bank', '—'],
  ]
  const metaItems = [
    `Opened: ${formatDateTime(alert.opened_at)}`,
    `SLA remaining: ${formatDuration(slaRemainingSeconds)}`,
    `Priority: ${alert.priority || '—'}`,
  ]
  const footerItems = [
    `INCIDENT REF: ${alert.incident_ref || alert.id}`,
    `AUTOMATION: ${alert.automation_action || '—'}`,
    `QUEUE TIME: ${formatDuration(alert.queue_time)}`,
    `SECURITY LEVEL: ${alert.tier || alert.severity}`,
  ]
  const explanation = alert.explanation?.summary || alert.rule_key || 'Alert details'

  return (
    <main className="app-shell">
      <Sidebar activeItem="Alert Queue" analystId={analystId} onNavigate={onNavigate} />
      <section className="app-content alert-detail-content" aria-label="Alert detail workspace">
        <div className="min-h-full">
          <div className="min-h-full bg-[#f7f8f7]">
            <div className="flex flex-wrap items-center gap-[12px] border-b border-[#dfe5e3] bg-[#fdfdfd] px-[22px] py-[12px] font-mono text-[10px] text-[#53615d]">
              <div className="flex items-center gap-[8px] whitespace-nowrap">
                <button type="button" onClick={onBack} className="text-[#384b48]" aria-label="Back to alert queue">←</button>
                <span>Alert queue / {alert.incident_ref || alert.id}</span>
              </div>

              <span className={`inline-flex items-center rounded-full px-[8px] py-[3px] text-[8px] font-medium ${alert.tier === 'high' ? 'bg-[#f8dfe0] text-[#7d3d44]' : 'bg-[#eef2f1] text-[#53615d]'}`}>
                {alert.tier || alert.severity} tier
              </span>
              <span>Entity: {flaggedAccount?.external_ref || '—'}</span>
            </div>

            <div className="border-b border-[#e7ebea] bg-[#fafbfa] px-[22px] py-[8px]">
              <div className="flex flex-wrap items-center gap-[8px] font-mono text-[9px] text-[#586866]">
                {metaItems.map((item, index) => (
                  <div key={item} className="flex items-center gap-[8px]">
                    <span>{item}</span>
                    {index < metaItems.length - 1 && <span className="text-[#9aa6a3]">·</span>}
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-[18px] p-[22px] xl:grid-cols-[35%_65%]">
              <div className="border border-[#dfe5e3] bg-[#fdfdfd]">
                <div className="flex items-center justify-between border-b border-[#edf1f0] px-[14px] py-[12px]">
                  <span className="font-mono text-[9px] font-medium uppercase tracking-[0.08em] text-[#667572]">Flagged account</span>
                  <span className="inline-flex items-center rounded-full bg-[#eef2f1] px-[8px] py-[3px] font-mono text-[7px] font-medium uppercase tracking-[0.06em] text-[#53615d]">
                    {flaggedAccount?.jurisdiction || 'ACCOUNT'}
                  </span>
                </div>

                <div className="px-[14px] pb-[12px] pt-[14px]">
                  <h1 className="text-[22px] font-semibold tracking-[-0.04em] text-[#1b2a27]" style={{ fontFamily: 'Inter, sans-serif' }}>
                    {flaggedAccount?.name || flaggedAccount?.external_ref || 'Account'}
                  </h1>
                  <p className="mt-[4px] font-mono text-[9px] text-[#5c6d69]">ID: {flaggedAccount?.external_ref || flaggedAccount?.id}</p>

                  <div className="mt-[16px] border-t border-[#dfe5e3] pt-[10px]">
                    <p className="font-mono text-[8px] font-medium uppercase tracking-[0.08em] text-[#667572]">Trigger transaction amount</p>
                    <p className="mt-[5px] text-[26px] font-semibold tracking-[-0.05em] text-[#1c2a29]" style={{ fontFamily: 'Inter, sans-serif' }}>
                      {formatMoney(triggerTransaction?.amount, triggerTransaction?.currency)}
                    </p>
                  </div>
                </div>

                <div className="border-t border-[#dfe5e3]">
                  {accountRows.map(([label, value]) => {
                    const isBeneficiaryRow = label === 'Beneficiary entity'
                    const displayValue = Array.isArray(value) ? value : [value]

                    return (
                      <div key={label} className="grid min-h-[34px] grid-cols-[110px_1fr] items-center border-b border-[#edf1f0] px-[14px] py-[8px] last:border-b-0">
                        <span className="text-[9px] font-medium tracking-[-0.01em] text-[#687772]" style={{ fontFamily: 'Inter, sans-serif' }}>{label}</span>
                        <span className="flex items-center justify-end gap-[4px] text-right font-mono text-[8px] leading-[1.5] text-[#2e3d3a] whitespace-pre-line break-words">
                          {displayValue.map((item, index) => (
                            <span key={`${label}-${index}`} className={isBeneficiaryRow && index === 1 ? 'inline' : ''}>{item}</span>
                          ))}
                        </span>
                      </div>
                    )
                  })}
                </div>

                <div className="border-t border-[#dfe5e3] px-[14px] py-[12px]">
                  <div className="flex items-center justify-between font-mono text-[8px] text-[#5d6d69]">
                    <span>RECENT ACCOUNT ACTIVITY ({alert.last_5_transactions.length} EVENTS)</span>
                    <span>UTC STANDARD</span>
                  </div>

                  <div className="mt-[10px] grid grid-cols-[1fr_0.7fr_0.8fr_0.8fr] gap-[8px] border-b border-[#edf1f0] pb-[6px] font-mono text-[7px] text-[#5e6d6a]">
                    <span>Timestamp</span>
                    <span className="text-right">Amount</span>
                    <span className="text-right">Route</span>
                    <span className="text-right">State</span>
                  </div>
                  <div className="mt-[4px] space-y-[4px]">
                    {alert.last_5_transactions.map((transaction) => (
                      <div key={transaction.id} className="grid grid-cols-[1fr_0.7fr_0.8fr_0.8fr] gap-[8px] font-mono text-[7px] text-[#344340]">
                        <span className="truncate">{formatDateTime(transaction.occurred_at)}</span>
                        <span className="text-right">{formatMoney(transaction.amount, transaction.currency)}</span>
                        <span className="text-right">{transaction.direction}</span>
                        <span className="text-right">{transaction.status}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="h-[120px] bg-[#d9d9d9]" aria-label="Reserved chart area" />

                <div className="flex items-center justify-between border-t border-[#dfe5e3] px-[14px] py-[12px] font-mono text-[8px] text-[#586866]">
                  <span>KYC Ref: {flaggedAccount?.kyc_ref || '—'}</span>
                  <span>Risk Index: {flaggedAccount?.risk_index ?? '—'}/100</span>
                </div>
              </div>

              <div className="border border-[#dfe5e3] bg-[#fdfdfd]">
                <div className="flex items-center justify-between border-b border-[#edf1f0] px-[14px] py-[12px]">
                  <h2 className="flex items-center gap-[7px] text-[11px] font-semibold text-[#1d2a29]" style={{ fontFamily: 'Inter, sans-serif' }}>
                    <span className="text-[#173d39]">■</span>
                    Contributing risk factors
                  </h2>
                  <span className="font-mono text-[7px] text-[#63726f]">MODEL: {alert.model_version || '—'}</span>
                </div>

                <div className="p-[14px]">
                  <div className="border border-[#efb4ae] bg-[#f9d8d4] p-[10px]">
                    <p className="text-[10px] font-bold text-[#2d2d2d]" style={{ fontFamily: 'Inter, sans-serif' }}>
                      {explanation}
                    </p>
                    <p className="mt-[5px] text-[9px] leading-[1.4] text-[#704e4a]" style={{ fontFamily: 'Inter, sans-serif' }}>
                      {alert.rule_key || alert.source}
                    </p>
                  </div>

                  <div className="mt-[14px] space-y-[12px]">
                    {alert.risk_factors.map((item, index) => (
                      <div key={`${item.title}-${index}`} className="border-b border-[#edf1f0] pb-[12px] last:border-b-0 last:pb-0">
                        <div className="flex items-center justify-between gap-[8px]">
                          <p className="text-[10px] font-semibold text-[#1c2a29]" style={{ fontFamily: 'Inter, sans-serif' }}>{item.title}</p>
                          <span className="shrink-0 font-mono text-[7px] font-medium text-[#5d6d69]">Weight: {item.weight_pct}%</span>
                        </div>

                        <WeightBar percent={item.weight_pct} />

                        <p className="mt-[8px] text-[8px] leading-[1.45] text-[#697773]" style={{ fontFamily: 'Inter, sans-serif' }}>{item.description}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-[18px] grid gap-[7px] md:grid-cols-3">
                    {[
                      ['Risk Profile', `${alert.risk_score}`],
                      ['Alert Source', alert.source],
                      ['Rule Trigger', alert.rule_key || '—'],
                    ].map(([label, value]) => (
                      <div key={label} className="border border-[#dfe5e3] bg-[#f6f8f7] px-[7px] py-[7px]">
                        <p className="font-mono text-[6px] uppercase tracking-[0.08em] text-[#64716e]">{label}</p>
                        <p className="mt-[5px] font-mono text-[7px] font-medium text-[#2d3b38]">{value}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-[18px] flex flex-col gap-[8px] sm:flex-row">
                    <div className="flex min-w-0 flex-1 items-center border border-[#dfe5e3] bg-[#fbfcfb] px-[8px] py-[6px]">
                      <span className="mr-[6px] font-mono text-[9px] text-[#687973]">&gt;</span>
                      <input
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        className="min-w-0 flex-1 bg-transparent font-mono text-[8px] text-[#2b3735] outline-none placeholder:text-[#8a9793]"
                        placeholder="Add analyst notes (optional)..."
                        aria-label="Add analyst notes"
                        style={{ fontFamily: '"JetBrains Mono", monospace' }}
                      />
                    </div>

                    <div className="flex items-center gap-[8px]">
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => void handleDecision('false_positive')}
                        className="h-[32px] border border-[#cfd8d6] bg-white px-[10px] text-[8px] font-medium text-[#334340]"
                        style={{ fontFamily: 'Inter, sans-serif' }}
                      >
                        Mark as false positive
                      </button>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => void handleDecision('confirmed_fraud')}
                        className="h-[32px] bg-[#1d403e] px-[12px] text-[8px] font-semibold text-white"
                        style={{ fontFamily: 'Inter, sans-serif' }}
                      >
                        Confirm fraud
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="border-t border-[#e3e8e5] bg-[#f9faf9] px-[20px] py-[10px]">
              <div className="flex flex-wrap items-center gap-[6px] font-mono text-[9px] text-[#4e5d5a]">
                {footerItems.map((item, index) => (
                  <div key={item} className="flex items-center gap-[6px]">
                    <span>{item}</span>
                    {index < footerItems.length - 1 && <span className="text-[#a0aaa7]">|</span>}
                  </div>
                ))}
              </div>
            </div>
            {error && (
              <p className="border-t border-[#efb4ae] bg-[#f9d8d4] px-[20px] py-[8px] font-mono text-[8px] text-[#704e4a]" role="alert">
                {error}
              </p>
            )}
          </div>
        </div>
      </section>
    </main>
  )
}

function readAppRoute() {
  if (typeof window === 'undefined') return { page: 'alert', caseId: null }
  if (window.location.pathname === '/settings') return { page: 'settings', caseId: null }
  const linkedAccountsMatch = window.location.pathname.match(/^\/investigations\/([^/]+)\/linked-accounts$/)
  if (linkedAccountsMatch) return { page: 'linked-accounts', caseId: decodeURIComponent(linkedAccountsMatch[1]) }
  const caseMatch = window.location.pathname.match(/^\/investigations\/([^/]+)$/)
  if (caseMatch) return { page: 'investigations', caseId: decodeURIComponent(caseMatch[1]) }
  if (window.location.pathname === '/investigations') return { page: 'investigations', caseId: null }
  if (window.location.pathname === '/transactions') return { page: 'transactions', caseId: null }
  return { page: 'alert', caseId: null }
}

function App() {
  // TODO: replace with real API call
  const [mockSystemStatus] = useState(() => ({
    systemStatus: 'Operational',
    version: '2.4.9',
    node: 'US-EAST-88',
    tlsVersion: '1.3',
    connectionStatus: 'Active',
    auditId: typeof crypto !== 'undefined' ? crypto.randomUUID().slice(0, 8) : Math.random().toString(16).slice(2, 10),
    emailPlaceholder: 'analyst.4892@bankops.internal',
  }))
  const [analyst, setAnalyst] = useState(defaultAnalyst)
  const [passphrase, setPassphrase] = useState('')
  const [showPassphrase, setShowPassphrase] = useState(false)
  const [signedIn, setSignedIn] = useState(() => Boolean(getAccessToken()))
  const [analystId, setAnalystId] = useState(() => getAnalystId() || '')
  const [loginError, setLoginError] = useState('')
  const [isSigningIn, setIsSigningIn] = useState(false)
  const [settingsDirty, setSettingsDirty] = useState(false)
  const currentUser = {
    name: 'Eleni Vance',
    id: analystId,
    role: 'Senior Fraud Analyst / Tier 2 Escalations',
    sessionStatus: 'Active since 08:00 UTC',
  }
  const [route, setRoute] = useState(readAppRoute)
  const { page: activePage, caseId: selectedCaseId } = route

  useEffect(() => {
    function handlePopState() {
      if (activePage === 'settings' && settingsDirty && !window.confirm('You have unsaved settings. Leave this page?')) {
        const currentPath = route.page === 'alert' ? '/' : `/${route.page}`
        window.history.pushState({}, '', currentPath)
        return
      }
      setRoute(readAppRoute())
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [activePage, route, settingsDirty])

  useEffect(() => {
    if (activePage !== 'settings' || !settingsDirty) return undefined

    function warnBeforeUnload(event) {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [activePage, settingsDirty])

  function navigate(page, caseId = null) {
    setRoute({ page, caseId })
    const encodedCaseId = caseId ? encodeURIComponent(caseId) : null
    const path = page === 'linked-accounts' && encodedCaseId
      ? `/investigations/${encodedCaseId}/linked-accounts`
      : page === 'investigations' && encodedCaseId
        ? `/investigations/${encodedCaseId}`
        : page === 'alert' ? '/' : `/${page}`
    window.history.pushState({}, '', path)
  }

  function handleNavigate(page, caseId = null) {
    if (activePage === 'settings' && settingsDirty && page !== activePage && !window.confirm('You have unsaved settings. Leave this page?')) {
      return false
    }
    navigate(page, caseId)
    return true
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (isSigningIn) return
    setIsSigningIn(true)
    setLoginError('')
    try {
      const result = await login(analyst.trim(), passphrase)
      setAnalystId(result.analyst_id)
      setSignedIn(true)
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Unable to sign in. Please try again.')
    } finally {
      setIsSigningIn(false)
    }
  }

  if (signedIn) {
    if (activePage === 'transactions') {
      return (
        <SignedInLayout activeItem="Transactions" analystId={analystId} onNavigate={handleNavigate}>
          <TransactionsPage />
        </SignedInLayout>
      )
    }
    if (activePage === 'investigations') {
      return (
        <SignedInLayout activeItem="Investigations" analystId={analystId} onNavigate={handleNavigate}>
          <InvestigationsPage
            caseId={selectedCaseId}
            onOpenCase={(caseId) => navigate('investigations', caseId)}
            onBackToCases={() => navigate('investigations')}
            onOpenLinkedAccounts={(caseId) => navigate('linked-accounts', caseId)}
          />
        </SignedInLayout>
      )
    }
    if (activePage === 'linked-accounts') {
      return (
        <SignedInLayout activeItem="Investigations" analystId={analystId} onNavigate={handleNavigate}>
          <LinkedAccountsPage
            caseId={selectedCaseId}
            onBackToList={() => navigate('investigations')}
            onOpenCase={(caseId) => navigate('investigations', caseId)}
          />
        </SignedInLayout>
      )
    }
    if (activePage === 'settings') {
      return (
        <SignedInLayout activeItem="Settings" analystId={analystId} onNavigate={handleNavigate}>
          <SettingsPage
            currentUser={currentUser}
            onDirtyChange={setSettingsDirty}
            onSignOut={() => {
              if (handleNavigate('alert')) setSignedIn(false)
            }}
          />
        </SignedInLayout>
      )
    }

    return <AlertQueue analystId={analystId} onNavigate={handleNavigate} />
  }

  return (
    <main className="flex h-screen overflow-hidden bg-[#f7f8f7] text-[#25302f]">
      <section className="relative flex h-screen w-full shrink-0 flex-col border-r border-[#e2e7e4] bg-[#f3f5f4] px-[22px] py-[23px] lg:max-w-[312px]">
        <header className="border-b border-[#e4e9e7] pb-[21px]">
          <p className="font-display text-[18px] font-semibold tracking-[-0.02em] text-[#202a29]">Underlock</p>
          <p className="mt-[7px] font-mono text-[8px] leading-none tracking-[0.03em] text-[#52615e]">
            <span className="mr-[5px] text-[#1b4441]">●</span>
            System {mockSystemStatus.systemStatus} · v{mockSystemStatus.version}
          </p>
        </header>

        <div className="flex-1 pt-[24px]">
          <div className="mb-[25px]">
            <h1 className="font-display text-[14px] font-semibold tracking-[-0.015em] text-[#202a29]">Analyst Authentication</h1>
            <p className="mt-[7px] max-w-[245px] text-[9px] leading-[1.45] text-[#687471]">
              Internal monitoring gateway for authorized security personnel.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-[15px]">
            <label className="block">
              <span className="mb-[6px] block text-[8px] font-medium text-[#596663]">Analyst Code</span>
              <span className="flex h-[24px] items-center border border-[#dce2df] bg-[#fbfcfb] px-[7px] shadow-[0_1px_2px_rgba(20,35,32,0.02)] focus-within:border-[#5b7772]">
                <span className="mr-[6px] font-mono text-[9px] text-[#72807d]">&gt;</span>
                <input
                  value={analyst}
                  onChange={(event) => setAnalyst(event.target.value)}
                  className="min-w-0 flex-1 bg-transparent font-mono text-[9px] text-[#6b7774] outline-none placeholder:text-[#9aa4a1]"
                  placeholder={mockSystemStatus.emailPlaceholder}
                  aria-label="Analyst ID or Corporate Email"
                />
              </span>
            </label>

            <label className="block">
              <span className="mb-[6px] block text-[8px] font-medium text-[#596663]">Security Key or Passphrase</span>
              <span className="flex h-[24px] items-center border border-[#dce2df] bg-[#fbfcfb] px-[7px] shadow-[0_1px_2px_rgba(20,35,32,0.02)] focus-within:border-[#5b7772]">
                <input
                  type={showPassphrase ? 'text' : 'password'}
                  value={passphrase}
                  onChange={(event) => setPassphrase(event.target.value)}
                  className="min-w-0 flex-1 bg-transparent font-mono text-[10px] tracking-[0.12em] text-[#31403d] outline-none placeholder:text-[7px] placeholder:tracking-[0.05em] placeholder:text-[#aab5b2]"
                  aria-label="Security Key or Passphrase"
                />
                <button
                  type="button"
                  onClick={() => setShowPassphrase((visible) => !visible)}
                  className="ml-2 flex h-5 w-5 items-center justify-center text-[#5d7773] transition-colors hover:text-[#1e4b47]"
                  aria-label={showPassphrase ? 'Hide passphrase' : 'Show passphrase'}
                >
                  {showPassphrase ? <EyeOff size={14} strokeWidth={1.8} /> : <Eye size={14} strokeWidth={1.8} />}
                </button>
              </span>
            </label>

            <div className="flex h-[20px] items-center justify-between border border-[#dce2df] bg-[#f8faf9] px-[7px] font-mono text-[7px] text-[#65736f]">
              <span>
                Node {mockSystemStatus.node} · TLS {mockSystemStatus.tlsVersion}
              </span>
              <span className="font-sans text-[7px] text-[#1d4b47]">
                <span className="mr-[3px]">●</span>
                {mockSystemStatus.connectionStatus}
              </span>
            </div>

            <button
              type="submit"
              disabled={isSigningIn}
              className="h-[25px] w-full bg-[#1d403e] text-[9px] font-semibold text-white transition-colors hover:bg-[#275651] focus:outline-none focus:ring-2 focus:ring-[#8eaaa5] focus:ring-offset-2 focus:ring-offset-[#f3f5f4]"
            >
              {isSigningIn ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {loginError && (
            <p className="mt-3 text-center font-mono text-[8px] text-[#9b3f3f]" role="alert">
              {loginError}
            </p>
          )}

          {signedIn && (
            <p className="mt-3 text-center font-mono text-[8px] text-[#35635e]" role="status">
              Session authenticated for {analyst || 'analyst'}.
            </p>
          )}
        </div>

        <aside className="border border-[#dce2df] bg-[#fbfcfb] px-[9px] py-[10px] text-[8px] leading-[1.45] text-[#64716e]">
          <div className="flex gap-[7px]">
            <LockKeyhole className="mt-[1px] shrink-0 text-[#506b67]" size={14} strokeWidth={1.7} />
            <p className="font-sans">
              Restricted access — Internal security personnel only.<br />
              Keystrokes and sessions are logged for audit<br />
              compliance.
            </p>
          </div>
          <p className="mt-[7px] pl-[21px] font-mono text-[7px] text-[#78837f]">
            Audit ID: {mockSystemStatus.auditId} · SOC 2 Type II Compliant
          </p>
        </aside>
      </section>

      <section aria-label="Secure workspace" className="hidden h-full flex-1 overflow-y-auto grid-canvas-bg lg:block" />
    </main>
  )
}

export default App
