import { useEffect, useState } from 'react'
import { getAlerts } from './api/alerts.js'
import { createInvestigation, getInvestigationStats, getInvestigations } from './api/investigations.js'
import { InvestigationGraphPanel } from './LinkedAccounts.jsx'

const STATUS_TABS = ['All', 'Open', 'Under review', 'Closed']
const PAGE_SIZE = 25

function apiStatus(status) {
  return status === 'All' ? undefined : status.toLowerCase().replaceAll(' ', '_')
}

function displayStatus(status) {
  return status === 'under_review' ? 'Under review' : status.charAt(0).toUpperCase() + status.slice(1)
}

function formatDuration(seconds) {
  if (!seconds) return '0s'
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds % 60)
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`
}

export function useInvestigations({ status, search, page, reloadKey, enabled = true }) {
  const [result, setResult] = useState({ items: [], total: 0 })
  const [kpis, setKpis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!enabled) return undefined
    const controller = new AbortController()
    getInvestigations({
      status: apiStatus(status),
      search,
      page,
      pageSize: PAGE_SIZE,
    }, { signal: controller.signal })
      .then(setResult)
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message || 'Unable to load investigations.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    setLoading(true)
    setError('')
    return () => controller.abort()
  }, [status, search, page, reloadKey, enabled])

  useEffect(() => {
    if (!enabled) return undefined
    const controller = new AbortController()
    getInvestigationStats({ signal: controller.signal })
      .then(setKpis)
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message || 'Unable to load investigation stats.')
      })
    return () => controller.abort()
  }, [reloadKey, enabled])

  return { cases: result.items, total: result.total, pageSize: PAGE_SIZE, kpis, loading, error }
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
    { label: 'OPEN CASES', value: kpis?.open_count ?? '—', suffix: `/ ${kpis?.total_count ?? '—'} total` },
    { label: 'CASES ASSIGNED TO ME', value: kpis?.assigned_to_me ?? '—', suffix: 'active queue' },
    { label: 'AVG. CASE RESOLUTION TIME', value: kpis ? formatDuration(kpis.avg_resolution_time_seconds) : '—', suffix: 'average' },
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

function CasesToolbar({ query, onQueryChange, status, onStatusChange, onNewCase }) {
  return (
    <div className="investigations-toolbar">
      <label className="investigations-filter-input">
        <span aria-hidden="true">&gt;</span>
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search case ID or title..."
          aria-label="Search case ID or title"
        />
      </label>
      <div className="transactions-segmented investigations-segmented" aria-label="Filter cases by status">
        {STATUS_TABS.map((tab) => (
          <button key={tab} type="button" aria-pressed={status === tab} onClick={() => onStatusChange(tab)}>
            {tab}
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
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '$0'
  return `$${amount.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
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
                <td className="case-id-cell">{caseItem.case_code}</td>
                <td className="case-title-cell">{caseItem.title}</td>
                <td className="case-number-cell">{caseItem.linked_alerts ?? 0}</td>
                <td className="case-number-cell">{formatExposure(caseItem.combined_exposure)}</td>
                <td><span className={`case-status-badge case-status-${caseItem.status.replaceAll('_', '-')}`}>{displayStatus(caseItem.status)}</span></td>
                <td>{caseItem.assignee?.analyst_code ?? caseItem.assignee?.name ?? '--'}</td>
                <td className="case-time-cell">{relativeActivity(caseItem.last_activity)}</td>
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
  const [alerts, setAlerts] = useState([])
  const [selectedAlertIds, setSelectedAlertIds] = useState([])
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getAlerts({ status: null, page: 1, pageSize: 100 }, { signal: controller.signal })
      .then((response) => setAlerts(response.items))
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message || 'Unable to load alerts.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingAlerts(false)
      })
    return () => controller.abort()
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    const normalizedTitle = title.trim()
    if (!normalizedTitle || !selectedAlertIds.length || submitting) return
    setSubmitting(true)
    setError('')
    try {
      await onCreateCase(normalizedTitle, selectedAlertIds)
    } catch (requestError) {
      setError(requestError.message || 'Unable to create case.')
    } finally {
      setSubmitting(false)
    }
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
          <fieldset className="investigations-alert-picker">
            <legend>Alerts to link</legend>
            {loadingAlerts ? <p>Loading alerts…</p> : alerts.length ? alerts.map((alert) => (
              <label key={alert.id}>
                <input
                  type="checkbox"
                  checked={selectedAlertIds.includes(alert.id)}
                  onChange={(event) => {
                    setSelectedAlertIds((current) => event.target.checked
                      ? [...current, alert.id]
                      : current.filter((alertId) => alertId !== alert.id))
                  }}
                />
                <span>{alert.priority || alert.rule_key || alert.source} · risk {alert.risk_score} · {alert.status}</span>
              </label>
            )) : <p>No alerts available to link.</p>}
          </fieldset>
          {error && <p className="investigations-modal-error" role="alert">{error}</p>}
          <div className="investigations-modal-actions">
            <button className="transactions-export-button" type="button" onClick={onClose}>Cancel</button>
            <button className="transactions-export-button investigations-new-case" type="submit" disabled={submitting || loadingAlerts || !selectedAlertIds.length}>
              {submitting ? 'Creating…' : `Create case${selectedAlertIds.length ? ` (${selectedAlertIds.length})` : ''}`}
            </button>
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
      <InvestigationGraphPanel caseId={caseId} />
    </div>
  )
}

export default function InvestigationsPage({ caseId, onOpenCase, onBackToCases, onOpenLinkedAccounts }) {
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('All')
  const [newCaseOpen, setNewCaseOpen] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const { cases, total, pageSize, kpis, loading, error } = useInvestigations({
    status,
    search,
    page,
    reloadKey,
    enabled: !caseId,
  })

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setSearch(query.trim()), 250)
    return () => window.clearTimeout(timeoutId)
  }, [query])

  const pageCount = Math.ceil(total / pageSize)

  if (caseId) return <main className="transactions-page investigations-page"><CaseDetailStub caseId={caseId} onBack={onBackToCases} onOpenLinkedAccounts={onOpenLinkedAccounts} /></main>

  function updateQuery(value) {
    setQuery(value)
    setPage(1)
  }

  function updateStatus(value) {
    setStatus(value)
    setPage(1)
  }

  async function handleCreateCase(title, alertIds) {
    await createInvestigation({ title, alert_ids: alertIds })
    setQuery('')
    setSearch('')
    setStatus('All')
    setPage(1)
    setReloadKey((current) => current + 1)
    setNewCaseOpen(false)
  }

  return (
    <main className="transactions-page investigations-page">
      <PageHeader />
      <KpiStrip kpis={kpis} />
      <CasesToolbar query={query} onQueryChange={updateQuery} status={status} onStatusChange={updateStatus} onNewCase={() => setNewCaseOpen(true)} />
      {error && <p className="investigations-request-error" role="alert">{error}</p>}
      <section className="investigations-table-section" aria-label="Cases">
        {loading && !cases.length
          ? <p className="investigations-loading" role="status">Loading investigations…</p>
          : <CasesTable cases={cases} onOpenCase={onOpenCase} onOpenLinkedAccounts={onOpenLinkedAccounts} />}
        <TablePagination page={page} pageCount={pageCount} totalCount={total} pageSize={pageSize} onPageChange={setPage} />
      </section>
      {newCaseOpen && <NewCaseModal onClose={() => setNewCaseOpen(false)} onCreateCase={handleCreateCase} />}
    </main>
  )
}