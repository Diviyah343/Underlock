import { useEffect, useState } from 'react'
import { Eye, EyeOff, LockKeyhole, UserRound } from 'lucide-react'
import TransactionsPage from './Transactions.jsx'
import InvestigationsPage from './Investigations.jsx'
import LinkedAccountsPage from './LinkedAccounts.jsx'
import SettingsPage from './Settings.jsx'

const defaultAnalyst = 'analyst.4092@bankops.internal'

const riskFactors = [
  ['Geographic velocity anomaly', 'Session initiated from [LOCATION] IP 0h 0m after Antwerp physical terminal authentication.'],
  ['Amount deviation from historical baseline', 'Transfer of $000,000.00 is 0.0x higher than typical operational ceiling ($00,000,000.00).'],
  ['Unrecognized beneficiary entity', 'First-time counterparty added 42 minutes prior to wire submission without two-person rule verification.'],
  ['Device fingerprint divergence', 'Unregistered browser profile and novel TLS client hello fingerprint for authorized corporate signer.'],
]

function WeightBar({ percent }) {
  const safePercent = Math.min(100, Math.max(0, Number(percent) || 0))

  return (
    <div className="mt-[8px] h-[4px] w-full overflow-hidden rounded-[2px] bg-[#e0e0e0]">
      <div className="h-full rounded-[2px] bg-[#1a1a1a]" style={{ width: `${safePercent}%` }} />
    </div>
  )
}

function Sidebar({ activeItem, onNavigate }) {
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
          <span>Analyst: <strong>AN-8902</strong></span>
        </div>
        <div className="app-sidebar-status">
          <span className="app-sidebar-node"><span aria-hidden="true" />NODE_04: LIVE</span>
          <span>Latency: <strong>14ms</strong></span>
        </div>
      </footer>
    </aside>
  )
}

function SignedInLayout({ activeItem, onNavigate, children }) {
  return (
    <main className="app-shell">
      <Sidebar activeItem={activeItem} onNavigate={onNavigate} />
      <section className="app-content" aria-label={`${activeItem} workspace`}>
        {children}
      </section>
    </main>
  )
}

function AlertDetail({ onNavigate }) {
  const metaItems = ['Opened: 14:38:12 UTC', 'SLA remaining: 11m 39s', 'Priority: P1-AML']
  const accountRows = [
    ['Location / IP', '[LOCATION]  [IP ADDRESS]'],
    ['Device signature', '[MODEL NAME AND NUMBER]'],
    ['Origin channel', '[]'],
    ['Beneficiary entity', ['[]', 'ACC']],
    ['Beneficiary bank', '[]'],
  ]
  const riskCards = [
    {
      title: 'Geographic velocity anomaly',
      weight: 82,
      description: 'Session initiated from [LOCATION] IP 0h 0m after Antwerp physical terminal authentication.',
    },
    {
      title: 'Amount deviation from historical baseline',
      weight: 67,
      description: 'Transfer of $000,000.00 is 0.0x higher than typical operational ceiling ($00,000,000.00).',
    },
    {
      title: 'Unrecognized beneficiary entity',
      weight: 54,
      description: 'First-time counterparty added 42 minutes prior to wire submission without two-person rule verification.',
    },
    {
      title: 'Device fingerprint divergence',
      weight: 79,
      description: 'Unregistered browser profile and novel TLS client hello fingerprint for authorized corporate signer.',
    },
  ]
  const footerItems = [
    'INCIDENT REF: INC-499128-X',
    'AUTOMATION: HOLD_DISBURSEMENT [ACTIVE]',
    'SIGNATURE: ECDSA-SHA256:4f9a0c',
    'QUEUE TIME: 00:04:18',
    'SECURITY LEVEL: RESTRICTED',
  ]

  return (
    <main className="app-shell">
      <Sidebar activeItem="Alert Queue" onNavigate={onNavigate} />
      <section className="app-content alert-detail-content" aria-label="Alert detail workspace">
        <div className="min-h-full">
          <div className="min-h-full bg-[#f7f8f7]">
            <div className="flex flex-wrap items-center gap-[12px] border-b border-[#dfe5e3] bg-[#fdfdfd] px-[22px] py-[12px] font-mono text-[10px] text-[#53615d]">
              <div className="flex items-center gap-[8px] whitespace-nowrap">
                <span className="text-[#384b48]">←</span>
                <span>Alert queue / ALT-N0000</span>
              </div>

              <span className="inline-flex items-center rounded-full bg-[#f8dfe0] px-[8px] py-[3px] text-[8px] font-medium text-[#7d3d44]">
                High tier
              </span>
              <span>Entity: ACC</span>
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
                    TIER-1 CORPORATE
                  </span>
                </div>

                <div className="px-[14px] pb-[12px] pt-[14px]">
                  <h1 className="text-[22px] font-semibold tracking-[-0.04em] text-[#1b2a27]" style={{ fontFamily: 'Inter, sans-serif' }}>
                    [ACCOUNT NAME]
                  </h1>
                  <p className="mt-[4px] font-mono text-[9px] text-[#5c6d69]">ID: ACC-9011-82</p>

                  <div className="mt-[16px] border-t border-[#dfe5e3] pt-[10px]">
                    <p className="font-mono text-[8px] font-medium uppercase tracking-[0.08em] text-[#667572]">Trigger transaction amount</p>
                    <p className="mt-[5px] text-[26px] font-semibold tracking-[-0.05em] text-[#1c2a29]" style={{ fontFamily: 'Inter, sans-serif' }}>
                      $000,000.00
                      <span className="ml-[4px] align-middle font-mono text-[10px] font-medium tracking-normal text-[#5c6d69]">USD</span>
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
                    <span>RECENT ACCOUNT ACTIVITY (5 EVENTS)</span>
                    <span>UTC STANDARD</span>
                  </div>

                  <div className="mt-[10px] grid grid-cols-[1fr_0.7fr_0.8fr_0.8fr] gap-[8px] border-b border-[#edf1f0] pb-[6px] font-mono text-[7px] text-[#5e6d6a]">
                    <span>Timestamp</span>
                    <span className="text-right">Amount</span>
                    <span className="text-right">Route</span>
                    <span className="text-right">State</span>
                  </div>
                </div>

                <div className="h-[120px] bg-[#d9d9d9]" aria-label="Reserved chart area" />

                <div className="flex items-center justify-between border-t border-[#dfe5e3] px-[14px] py-[12px] font-mono text-[8px] text-[#586866]">
                  <span>KYC Ref: C-88192-A</span>
                  <span>Risk Index: 0/100</span>
                </div>
              </div>

              <div className="border border-[#dfe5e3] bg-[#fdfdfd]">
                <div className="flex items-center justify-between border-b border-[#edf1f0] px-[14px] py-[12px]">
                  <h2 className="flex items-center gap-[7px] text-[11px] font-semibold text-[#1d2a29]" style={{ fontFamily: 'Inter, sans-serif' }}>
                    <span className="text-[#173d39]">■</span>
                    Contributing risk factors
                  </h2>
                  <span className="font-mono text-[7px] text-[#63726f]">MODEL: HYDRA-V4.2 [SYN-DETECT]</span>
                </div>

                <div className="p-[14px]">
                  <div className="border border-[#efb4ae] bg-[#f9d8d4] p-[10px]">
                    <p className="text-[10px] font-bold text-[#2d2d2d]" style={{ fontFamily: 'Inter, sans-serif' }}>
                      Flagged for unusual location and transaction velocity
                    </p>
                    <p className="mt-[5px] text-[9px] leading-[1.4] text-[#704e4a]" style={{ fontFamily: 'Inter, sans-serif' }}>
                      Transaction originating from [PLACE], C departs from 90-day baseline. Amount exceeds 30-day average transaction size by 0% within 0 hours of prior settlement.
                    </p>
                  </div>

                  <div className="mt-[14px] space-y-[12px]">
                    {riskCards.map((item) => (
                      <div key={item.title} className="border-b border-[#edf1f0] pb-[12px] last:border-b-0 last:pb-0">
                        <div className="flex items-center justify-between gap-[8px]">
                          <p className="text-[10px] font-semibold text-[#1c2a29]" style={{ fontFamily: 'Inter, sans-serif' }}>{item.title}</p>
                          <span className="shrink-0 font-mono text-[7px] font-medium text-[#5d6d69]">Weight: {item.weight}%</span>
                        </div>

                        <WeightBar percent={item.weight} />

                        <p className="mt-[8px] text-[8px] leading-[1.45] text-[#697773]" style={{ fontFamily: 'Inter, sans-serif' }}>{item.description}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-[18px] grid gap-[7px] md:grid-cols-3">
                    {[
                      ['Risk Profile', 'HIGH DIVERGENCE'],
                      ['IP Reputation', 'DATACENTER PROXY'],
                      ['Rule Trigger', 'R-8882 (VELOCITY_SPIKE)'],
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
                        className="min-w-0 flex-1 bg-transparent font-mono text-[8px] text-[#2b3735] outline-none placeholder:text-[#8a9793]"
                        placeholder="Add analyst notes (optional)..."
                        aria-label="Add analyst notes"
                        style={{ fontFamily: '"JetBrains Mono", monospace' }}
                      />
                    </div>

                    <div className="flex items-center gap-[8px]">
                      <button
                        type="button"
                        className="h-[32px] border border-[#cfd8d6] bg-white px-[10px] text-[8px] font-medium text-[#334340]"
                        style={{ fontFamily: 'Inter, sans-serif' }}
                      >
                        Mark as false positive
                      </button>
                      <button
                        type="button"
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
          </div>
        </div>
      </section>
    </main>
  )
}

function AlertSummary() {
  const rows = [['Location / IP', '[LOCATION]  [IP ADDRESS]'], ['Device signature', '[MODEL NAME AND NUMBER]'], ['Origin channel', '[]'], ['Beneficiary entity', '[]\nACC'], ['Beneficiary bank', '[]']]
  return (
    <div className="border-r border-[#d5dcda]">
      <div className="border-b border-[#cbd3d0] px-[11px] py-[11px]">
        <div className="flex justify-between font-mono text-[7px] text-[#667572]"><span>FLAGGED ACCOUNT</span><span>TIER-1 CORPORATE</span></div>
        <h1 className="mt-[5px] text-[13px] font-bold tracking-[-0.025em]">[ACCOUNT NAME]</h1><p className="font-mono text-[7px] text-[#53625f]">ID: ACC-0012</p>
        <div className="mt-[10px] border-t border-[#cbd3d0] pt-[8px] font-mono"><p className="text-[7px] text-[#596966]">TRIGGER TRANSACTION AMOUNT</p><p className="mt-[2px] text-[17px] font-semibold tracking-[-0.04em]">$000,000.00 <span className="text-[7px] font-normal tracking-normal">USD</span></p></div>
      </div>
      {rows.map(([label, value]) => <div key={label} className="grid min-h-[27px] grid-cols-[94px_1fr] items-center border-b border-[#cbd3d0] px-[11px] font-mono text-[7px]"><span className="text-[#64716e]">{label}</span><span className="whitespace-pre-line break-words text-right text-[#303e3b]">{value}</span></div>)}
      <div className="border-b border-[#cbd3d0] px-[11px] py-[8px]"><div className="flex justify-between font-mono text-[7px] text-[#60706d]"><span>RECENT ACCOUNT ACTIVITY (5 EVENTS)</span><span>UTC STANDARD</span></div><div className="mt-[8px] grid grid-cols-4 font-mono text-[7px] text-[#52615e]"><span>Timestamp</span><span className="text-right">Amount</span><span className="col-span-2 text-right">Route&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;State</span></div></div>
      <div className="flex justify-between px-[11px] py-[8px] font-mono text-[7px] text-[#566663]"><span>KYC Ref: C-88192-A</span><span>Risk Index: 0/100</span></div><div className="h-[154px] bg-[#c7cecc]" />
    </div>
  )
}

function RiskPanel() {
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between border-b border-[#d5dcda] px-[11px] py-[11px]"><h2 className="flex items-center gap-[7px] text-[10px] font-semibold"><span className="text-[#173d39]">■</span> Contributing risk factors</h2><span className="font-mono text-[7px] text-[#63726f]">MODEL: HYDRA-V4.2 [SYN-DETECT]</span></div>
      <div className="p-[11px]">
        <div className="border border-[#efb4ae] bg-[#f9d8d4] px-[9px] py-[9px]"><p className="text-[9px] font-bold">Flagged for unusual location and transaction velocity</p><p className="mt-[5px] text-[8px] leading-[1.35] text-[#704e4a]">Transaction originating from [PLACE], C departs from 90-day baseline. Amount exceeds 30-day average transaction size by 0% within 0 hours of prior settlement.</p></div>
        <div className="mt-[10px] space-y-[7px]">{riskFactors.map(([title, detail]) => <div key={title} className="border border-[#cbd3d0] bg-white px-[9px] py-[8px]"><div className="flex items-center justify-between gap-4"><p className="text-[9px] font-medium">{title}</p><span className="shrink-0 font-mono text-[7px] font-semibold">Weight: 0%</span></div><p className="mt-[6px] text-[8px] text-[#6a7774]">{detail}</p></div>)}</div>
        <div className="mt-[19px] grid grid-cols-3 gap-[7px]">{[['RISK PROFILE', 'HIGH DIVERGENCE'], ['IP REPUTATION', 'DATACENTER PROXY'], ['RULE TRIGGER', 'R-8882 (VELOCITY_SPIKE)']].map(([label, value]) => <div key={label} className="border border-[#cbd3d0] bg-[#f6f8f7] px-[7px] py-[7px] font-mono"><p className="text-[7px] text-[#64716e]">{label}</p><p className="mt-[5px] text-[7px] text-[#344340]">{value}</p></div>)}</div>
      </div>
      <div className="mt-[13px] flex border-t border-[#cbd3d0] px-[11px] py-[10px]"><input className="h-[23px] min-w-0 flex-1 border border-[#cbd3d0] px-[7px] font-mono text-[7px] outline-none placeholder:text-[#788582] focus:border-[#56736e]" placeholder=">  Add analyst notes (optional)..." /><button type="button" className="h-[23px] border-y border-r border-[#cbd3d0] bg-white px-[8px] text-[8px] font-medium">Mark as false positive</button><button type="button" className="ml-[7px] h-[23px] bg-[#1d403e] px-[9px] text-[8px] font-medium text-white">Confirm fraud</button></div>
    </div>
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
  const [signedIn, setSignedIn] = useState(false)
  const [settingsDirty, setSettingsDirty] = useState(false)
  const [currentUser] = useState({
    name: 'Eleni Vance',
    id: 'AN-8902',
    role: 'Senior Fraud Analyst / Tier 2 Escalations',
    sessionStatus: 'Active since 08:00 UTC',
  })
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

  function handleSubmit(event) {
    event.preventDefault()
    setSignedIn(true)
  }

  if (signedIn) {
    if (activePage === 'transactions') {
      return (
        <SignedInLayout activeItem="Transactions" onNavigate={handleNavigate}>
          <TransactionsPage />
        </SignedInLayout>
      )
    }
    if (activePage === 'investigations') {
      return (
        <SignedInLayout activeItem="Investigations" onNavigate={handleNavigate}>
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
        <SignedInLayout activeItem="Investigations" onNavigate={handleNavigate}>
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
        <SignedInLayout activeItem="Settings" onNavigate={handleNavigate}>
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

    return (
      <AlertDetail onNavigate={handleNavigate} />
    )
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
              <span className="mb-[6px] block text-[8px] font-medium text-[#596663]">Analyst ID or Corporate Email</span>
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
              className="h-[25px] w-full bg-[#1d403e] text-[9px] font-semibold text-white transition-colors hover:bg-[#275651] focus:outline-none focus:ring-2 focus:ring-[#8eaaa5] focus:ring-offset-2 focus:ring-offset-[#f3f5f4]"
            >
              {signedIn ? 'Access Granted' : 'Sign in'}
            </button>
          </form>

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
