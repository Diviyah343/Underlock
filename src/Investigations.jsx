import { useEffect, useState } from 'react'

const STATUS_TABS = ['All', 'Open', 'Under review', 'Closed']
const CASES_STORAGE_KEY = 'underlock.investigations.cases'

function readStoredCases() {
  if (typeof window === 'undefined') return []
  try {
    const storedCases = JSON.parse(window.localStorage.getItem(CASES_STORAGE_KEY) ?? '[]')
    return Array.isArray(storedCases) ? storedCases : []
  } catch {
    return []
  }
}

export function useInvestigations() {
  // TODO: replace browser-local cases with the investigations API.
  const [cases, setCases] = useState(readStoredCases)
  const [page, setPage] = useState(1)
  const [summary, setSummary] = useState({
    totalCases: 128,
    averageResolutionSeconds: 0,
    resolutionTargetMinutes: 0,
  })

  useEffect(() => {
    try {
      window.localStorage.setItem(CASES_STORAGE_KEY, JSON.stringify(cases))
    } catch {
      // Keep in-memory creation working when browser storage is unavailable.
    }
  }, [cases])

  const pageSize = 10
  const openCount = cases.filter((caseItem) => caseItem.status === 'Open').length
  const myQueueCount = cases.filter((caseItem) => caseItem.assignedAnalystId === 'AN-8902').length
  const createCase = (title) => {
    const now = new Date().toISOString()
    const newCase = {
      id: `INV-${now.slice(0, 4)}-${String(Date.now()).slice(-6)}`,
      title: title.trim(),
      linkedAlerts: 0,
      combinedExposure: 0,
      status: 'Open',
      assignedAnalyst: 'AN-8902',
      assignedAnalystId: 'AN-8902',
      lastActivity: now,
      identifiers: [],
    }
    setCases((currentCases) => [newCase, ...currentCases])
    return newCase
  }

  return {
    cases,
    createCase,
    page,
    setPage,
    pageSize,
    setCases,
    setSummary,
    kpis: {
      openCount,
      totalCount: summary.totalCases + cases.length,
      myQueueCount,
      averageResolutionSeconds: summary.averageResolutionSeconds,
      resolutionTargetMinutes: summary.resolutionTargetMinutes,
    },
  }
}

function PageHeader() {
  return (
    <header className="investigations-page-header">
      <h1>Investigations</h1>
    </header>
  )
}

function KpiStrip({ kpis }) {
  const metrics = [
    { label: 'OPEN CASES', value: kpis.openCount, suffix: `/ ${kpis.totalCount} total` },
    { label: 'CASES ASSIGNED TO ME', value: kpis.myQueueCount ? kpis.myQueueCount : 'Nil', suffix: 'active queue' },
    { label: 'AVG. CASE RESOLUTION TIME', value: `${kpis.averageResolutionSeconds}s`, suffix: `target < ${kpis.resolutionTargetMinutes}m` },
  ]

  return (
    <section className="investigations-kpi-strip" aria-label="Investigation metrics">
      {metrics.map((metric) => (
        <div className="investigations-kpi-cell" key={metric.label}>
          <h2>{metric.label}</h2>
          <p><strong>{metric.value}</strong><span>{metric.suffix}</span></p>
        </div>
      ))}
    </section>
  )
}

function CasesToolbar({ cases, query, onQueryChange, status, onStatusChange, onNewCase }) {
  const counts = {
    All: cases.length,
    Open: cases.filter((caseItem) => caseItem.status === 'Open').length,
    'Under review': cases.filter((caseItem) => caseItem.status === 'Under review').length,
    Closed: cases.filter((caseItem) => caseItem.status === 'Closed').length,
  }

  return (
    <div className="investigations-toolbar">
      <label className="investigations-filter-input">
        <span aria-hidden="true">&gt;</span>
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Filter cases, entities, identifiers..."
          aria-label="Filter cases, entities, identifiers"
        />
      </label>
      <div className="transactions-segmented investigations-segmented" aria-label="Filter cases by status">
        {STATUS_TABS.map((tab) => (
          <button key={tab} type="button" aria-pressed={status === tab} onClick={() => onStatusChange(tab)}>
            {tab} ({counts[tab]})
          </button>
        ))}
      </div>
      <button className="transactions-export-button investigations-new-case" type="button" onClick={onNewCase}>
        <span aria-hidden="true">+</span> New case
      </button>
    </div>
  )
}

function formatExposure(value) {
  if (typeof value !== 'number') return value ?? '$0'
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function relativeActivity(value) {
  if (!value) return '--'
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime())
  const minutes = Math.floor(elapsed / 60000)
  if (minutes < 1) return 'now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function CasesTable({ cases, onOpenCase, onOpenLinkedAccounts }) {
  return (
    <div className="investigations-table-frame">
      <div className="investigations-table-scroll">
        <table className="investigations-table">
          <colgroup>
            <col className="case-id-column" />
            <col className="case-title-column" />
            <col className="case-alerts-column" />
            <col className="case-exposure-column" />
            <col className="case-status-column" />
            <col className="case-analyst-column" />
            <col className="case-activity-column" />
            <col className="case-actions-column" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">CASE ID</th>
              <th scope="col">CASE TITLE</th>
              <th scope="col" className="case-number-heading">LINKED<br />ALERTS</th>
              <th scope="col" className="case-number-heading">COMBINED<br />EXPOSURE</th>
              <th scope="col">STATUS</th>
              <th scope="col">ASSIGNED<br />ANALYST</th>
              <th scope="col">LAST ACTIVITY</th>
              <th scope="col">ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {cases.length ? cases.map((caseItem) => (
              <tr
                key={caseItem.id}
                tabIndex={0}
                aria-label={`Open case ${caseItem.id}: ${caseItem.title}`}
                onClick={() => onOpenCase(caseItem.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onOpenCase(caseItem.id)
                  }
                }}
              >
                <td className="case-id-cell">{caseItem.id}</td>
                <td className="case-title-cell">{caseItem.title}</td>
                <td className="case-number-cell">{caseItem.linkedAlerts ?? 0}</td>
                <td className="case-number-cell">{formatExposure(caseItem.combinedExposure)}</td>
                <td><span className={`case-status-badge case-status-${String(caseItem.status).toLowerCase().replaceAll(' ', '-')}`}>{caseItem.status}</span></td>
                <td>{caseItem.assignedAnalyst ?? '--'}</td>
                <td className="case-time-cell">{relativeActivity(caseItem.lastActivity)}</td>
                <td className="case-actions-cell">
                  <button
                    type="button"
                    aria-label={`View linked accounts for ${caseItem.id}`}
                    onClick={(event) => {
                      event.stopPropagation()
                      onOpenLinkedAccounts(caseItem.id)
                    }}
                  >
                    Linked accounts
                  </button>
                </td>
              </tr>
            )) : (
              <tr className="investigations-empty-row">
                <td colSpan={8}>No cases yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TablePagination({ page, pageCount, totalCount, pageSize, onPageChange }) {
  const start = totalCount ? ((page - 1) * pageSize) + 1 : 0
  const end = Math.min(page * pageSize, totalCount)
  const displayedPage = pageCount ? page : 0
  const displayedRange = totalCount ? `${start}–${end}` : '0'

  return (
    <footer className="investigations-pagination">
      <p>Showing <strong>{displayedRange}</strong> of <strong>{totalCount}</strong> cases</p>
      <nav aria-label="Cases pagination">
        <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>&lt; Prev</button>
        <span>Page <strong>{displayedPage}</strong> of <strong>{pageCount}</strong></span>
        <button type="button" disabled={pageCount === 0 || page >= pageCount} onClick={() => onPageChange(page + 1)}>Next &gt;</button>
      </nav>
    </footer>
  )
}

function NewCaseModal({ onClose, onCreateCase }) {
  const [title, setTitle] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    const normalizedTitle = title.trim()
    if (!normalizedTitle) return
    onCreateCase(normalizedTitle)
  }

  return (
    <div className="investigations-modal-backdrop">
      <section className="investigations-modal" role="dialog" aria-modal="true" aria-labelledby="new-case-title">
        <header>
          <h2 id="new-case-title">New case</h2>
          <button type="button" aria-label="Close new case dialog" onClick={onClose}>×</button>
        </header>
        <form onSubmit={handleSubmit}>
          <label htmlFor="new-case-name">Case title</label>
          <input id="new-case-name" value={title} onChange={(event) => setTitle(event.target.value)} autoFocus required />
          <div className="investigations-modal-actions">
            <button className="transactions-export-button" type="button" onClick={onClose}>Cancel</button>
            <button className="transactions-export-button investigations-new-case" type="submit">Create case</button>
          </div>
        </form>
      </section>
    </div>
  )
}

function CaseDetailStub({ caseId, onBack, onOpenLinkedAccounts }) {
  return (
    <div className="investigations-detail-stub">
      <button className="transactions-export-button" type="button" onClick={onBack}>&lt; Back to cases</button>
      <button className="transactions-export-button linked-account-case-link" type="button" onClick={() => onOpenLinkedAccounts(caseId)}>Linked accounts</button>
      <h1>Case {caseId}</h1>
      <p>Case details are not connected yet.</p>
    </div>
  )
}

export default function InvestigationsPage({ caseId, onOpenCase, onBackToCases, onOpenLinkedAccounts }) {
  const { cases, createCase, page, setPage, pageSize, kpis } = useInvestigations()
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('All')
  const [newCaseOpen, setNewCaseOpen] = useState(false)
  const normalizedQuery = query.trim().toLowerCase()
  const filteredCases = cases.filter((caseItem) => {
    if (status !== 'All' && caseItem.status !== status) return false
    const searchable = [caseItem.id, caseItem.title, caseItem.entity, ...(caseItem.identifiers ?? [])].join(' ').toLowerCase()
    return searchable.includes(normalizedQuery)
  })
  const pageCount = Math.ceil(filteredCases.length / pageSize)
  const pageCases = filteredCases.slice((page - 1) * pageSize, page * pageSize)

  if (caseId) return <main className="transactions-page investigations-page"><CaseDetailStub caseId={caseId} onBack={onBackToCases} onOpenLinkedAccounts={onOpenLinkedAccounts} /></main>

  function updateQuery(value) {
    setQuery(value)
    setPage(1)
  }

  function updateStatus(value) {
    setStatus(value)
    setPage(1)
  }

  function handleCreateCase(title) {
    createCase(title)
    setQuery('')
    setStatus('All')
    setPage(1)
    setNewCaseOpen(false)
  }

  return (
    <main className="transactions-page investigations-page">
      <PageHeader />
      <KpiStrip kpis={kpis} />
      <CasesToolbar cases={cases} query={query} onQueryChange={updateQuery} status={status} onStatusChange={updateStatus} onNewCase={() => setNewCaseOpen(true)} />
      <section className="investigations-table-section" aria-label="Cases">
        <CasesTable cases={pageCases} onOpenCase={onOpenCase} onOpenLinkedAccounts={onOpenLinkedAccounts} />
        <TablePagination page={page} pageCount={pageCount} totalCount={filteredCases.length} pageSize={pageSize} onPageChange={setPage} />
      </section>
      {newCaseOpen && <NewCaseModal onClose={() => setNewCaseOpen(false)} onCreateCase={handleCreateCase} />}
    </main>
  )
}