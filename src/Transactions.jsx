import { useEffect, useRef, useState } from 'react'

const WINDOWS = {
  'Last 24h': { duration: 24 * 60 * 60 * 1000, labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', 'NOW'] },
  '1h': { duration: 60 * 60 * 1000, labels: ['-60m', '-50m', '-40m', '-30m', '-20m', '-10m', 'NOW'] },
  Live: { duration: 60 * 1000, labels: ['-60s', '-50s', '-40s', '-30s', '-20s', '-10s', 'NOW'] },
}

export function useTransactionStream() {
  const [transactions, setTransactions] = useState([])
  const [threshold, setThreshold] = useState(0.45)

  // Plug a WebSocket, SSE, or polling source into this hook when the feed is available.
  const now = Date.now()
  const recentTransactions = transactions.filter((transaction) => now - new Date(transaction.timestamp).getTime() <= 1000)
  const flaggedTransactions = transactions.filter((transaction) => transaction.status === 'Flagged')
  const fraudAverage = transactions.length ? (flaggedTransactions.length / transactions.length) * 100 : 0
  const hourlyFraud = new Map()
  transactions.forEach((transaction) => {
    const hour = Math.floor(new Date(transaction.timestamp).getTime() / (60 * 60 * 1000))
    const totals = hourlyFraud.get(hour) ?? { count: 0, flagged: 0 }
    totals.count += 1
    if (transaction.status === 'Flagged') totals.flagged += 1
    hourlyFraud.set(hour, totals)
  })
  const fraudPeak = Math.max(0, ...Array.from(hourlyFraud.values(), (totals) => (totals.flagged / totals.count) * 100))
  const currentHour = Math.floor(now / (60 * 60 * 1000))
  const historicalHours = Array.from(hourlyFraud.entries()).filter(([hour]) => hour !== currentHour).map(([, totals]) => totals.count)
  const hourlyMean = historicalHours.length ? historicalHours.reduce((sum, count) => sum + count, 0) / historicalHours.length : 0
  const currentHourCount = hourlyFraud.get(currentHour)?.count ?? 0
  const volumeChange = hourlyMean ? ((currentHourCount - hourlyMean) / hourlyMean) * 100 : 0
  const pushTransactions = (incoming) => {
    const updates = Array.isArray(incoming) ? incoming : [incoming]
    setTransactions((current) => [...current, ...updates].slice(-100))
  }

  return {
    transactions: transactions.slice(-100),
    metrics: {
      throughput: recentTransactions.length,
      volume: transactions.length,
      volumeChange,
      fraudAverage,
      fraudPeak,
      threshold,
    },
    pushTransactions,
    setThreshold,
  }
}

function formatCount(value) {
  const padded = String(value).padStart(8, '0')
  return `${padded.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} tx`
}

function seriesFor(transactions, period, metric) {
  const window = WINDOWS[period]
  const now = Date.now()
  const inWindow = transactions.filter((transaction) => {
    const age = now - new Date(transaction.timestamp).getTime()
    return age >= 0 && age <= window.duration
  })
  if (!inWindow.length) return []
  const buckets = Array.from({ length: window.labels.length }, () => ({ count: 0, flagged: 0 }))

  inWindow.forEach((transaction) => {
    const age = now - new Date(transaction.timestamp).getTime()
    const index = Math.min(buckets.length - 1, Math.floor(((window.duration - age) / window.duration) * buckets.length))
    buckets[index].count += 1
    if (transaction.status === 'Flagged') buckets[index].flagged += 1
  })

  return buckets.map((bucket) => metric === 'volume'
    ? bucket.count
    : (bucket.count ? (bucket.flagged / bucket.count) * 100 : 0))
}

function PageHeader({ period, onPeriodChange, throughput, paused }) {
  return (
    <header className="transactions-header">
      <div className="transactions-title-group">
        <h1>Live transactions</h1>
        <span className={`transactions-stream-badge ${paused ? 'is-paused' : ''}`}>
          <span className="transactions-status-square" aria-hidden="true" />
          {paused ? 'PAUSED' : 'STREAMING'}
        </span>
      </div>
      <div className="transactions-header-tools">
        <span className="transactions-throughput">Throughput: {throughput} tx/s</span>
        <span className="transactions-header-divider" aria-hidden="true" />
        <div className="transactions-segmented" aria-label="Chart time range">
          {Object.keys(WINDOWS).map((option) => (
            <button key={option} type="button" aria-pressed={period === option} onClick={() => onPeriodChange(option)}>
              {option === 'Last 24h' ? 'Last 24h' : option}
            </button>
          ))}
        </div>
      </div>
    </header>
  )
}

function ChartSvg({ title, values, labels, yTicks, maxValue, threshold, emptyMarker }) {
  const width = 800
  const height = 260
  const plot = { left: 72, right: 786, top: 18, bottom: 218 }
  const plotWidth = plot.right - plot.left
  const plotHeight = plot.bottom - plot.top
  const points = values.map((value, index) => ({
    x: plot.left + (plotWidth * index) / Math.max(values.length - 1, 1),
    y: plot.bottom - (Math.min(value, maxValue) / maxValue) * plotHeight,
  }))
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  const markerY = plot.bottom - (Math.min(emptyMarker, maxValue) / maxValue) * plotHeight
  const thresholdY = plot.bottom - (threshold / maxValue) * plotHeight

  return (
    <svg className="transactions-chart-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={title}>
      {yTicks.map((tick) => {
        const y = plot.bottom - (tick.value / maxValue) * plotHeight
        return (
          <g key={tick.label}>
            <line className={tick.value === 0 ? 'chart-baseline' : 'chart-gridline'} x1={plot.left} x2={plot.right} y1={y} y2={y} />
            <text className="chart-axis-label" x={plot.left - 10} y={y + 4} textAnchor="end">{tick.label}</text>
          </g>
        )
      })}
      {threshold !== undefined && (
        <g>
          <line className="chart-threshold" x1={plot.left} x2={plot.right} y1={thresholdY} y2={thresholdY} />
          <text className="chart-threshold-label" x={plot.right - 2} y={thresholdY - 7} textAnchor="end">LIM {threshold.toFixed(2)}%</text>
        </g>
      )}
      {values.length > 0 ? (
        <path className="chart-series" d={linePath} />
      ) : (
        <circle className="chart-empty-marker" cx={plot.right} cy={markerY} r="4" />
      )}
      {labels.map((label, index) => {
        const x = plot.left + (plotWidth * index) / Math.max(labels.length - 1, 1)
        return <text key={label} className={`chart-axis-label ${label === 'NOW' ? 'chart-now-label' : ''}`} x={x} y={height - 8} textAnchor="middle">{label}</text>
      })}
    </svg>
  )
}

function MetricCard({ title, subtitle, value, detail, series, period, yTicks, maxValue, threshold, emptyMarker, chartTitle }) {
  return (
    <article className="transactions-metric-card">
      <div className="transactions-metric-heading">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <div className="transactions-metric-value">
          <strong>{value}</strong>
          <span>{detail}</span>
        </div>
      </div>
      <ChartSvg
        title={chartTitle}
        values={series}
        labels={WINDOWS[period].labels}
        yTicks={yTicks}
        maxValue={maxValue}
        threshold={threshold}
        emptyMarker={emptyMarker}
      />
    </article>
  )
}

function FilterBar({ transactions, query, onQueryChange, segment, onSegmentChange, filteredRows }) {
  const counts = {
    all: transactions.length,
    review: transactions.filter((transaction) => transaction.status === 'Review').length,
    flagged: transactions.filter((transaction) => transaction.status === 'Flagged').length,
  }
  const tabs = [
    { label: `All (${counts.all})`, value: 'All' },
    { label: `Review (${counts.review})`, value: 'Review' },
    { label: `Flagged (${counts.flagged})`, value: 'Flagged' },
  ]

  function exportCsv() {
    const columns = ['Time', 'Tx hash', 'Account', 'Amount', 'Jurisdiction', 'Risk score', 'Status']
    const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const rows = filteredRows.map((transaction) => [
      transaction.timestamp,
      transaction.hash,
      transaction.account,
      `${transaction.amount} ${transaction.currency ?? ''}`.trim(),
      transaction.jurisdiction,
      transaction.riskScore,
      transaction.status,
    ])
    const csv = [columns, ...rows].map((row) => row.map(escape).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'transactions.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="transactions-filter-bar">
      <label className="transactions-filter-input">
        <span aria-hidden="true">&gt;</span>
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Filter accounts, hashes, jurisdictions..." aria-label="Filter accounts, hashes, jurisdictions" />
      </label>
      <div className="transactions-filter-actions">
        <div className="transactions-segmented transactions-filter-tabs" aria-label="Filter transaction status">
          {tabs.map((tab) => (
            <button key={tab.value} type="button" aria-pressed={segment === tab.value} onClick={() => onSegmentChange(tab.value)}>
              {tab.label}
            </button>
          ))}
        </div>
        <button className="transactions-export-button" type="button" onClick={exportCsv}>Export CSV</button>
      </div>
    </div>
  )
}

function FeedStatusBar({ paused, onTogglePaused, onJumpToLatest }) {
  return (
    <div className="transactions-feed-status">
      <div className="transactions-feed-status-copy" aria-live="polite">
        <span>Displaying 100 most recent transactions</span>
        <span className="transactions-status-separator" aria-hidden="true">·</span>
        <span className={`transactions-status-square ${paused ? 'is-muted' : ''}`} aria-hidden="true" />
        <span className="transactions-auto-scroll-label">{paused ? 'Feed paused' : 'Auto-scroll active'}</span>
      </div>
      <div className="transactions-feed-buttons">
        <button type="button" aria-pressed={!paused} onClick={onTogglePaused}>{paused ? 'Resume feed' : 'Pause feed'}</button>
        <button type="button" onClick={onJumpToLatest}>Jump to latest</button>
      </div>
    </div>
  )
}

function TransactionTable({ rows, scrollRef }) {
  const columns = ['Time', 'Tx hash', 'Account', 'Amount', 'Jurisdiction', 'Risk score', 'Status']

  return (
    <div className="transactions-table-scroll" ref={scrollRef}>
      <table className="transactions-table">
        <thead>
          <tr>{columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((transaction, index) => (
            <tr key={transaction.id ?? transaction.hash ?? index} className={`transaction-row-${String(transaction.status).toLowerCase()}`}>
              <td>{transaction.timestamp}</td>
              <td>{transaction.hash}</td>
              <td>{transaction.account}</td>
              <td>{transaction.amount} {transaction.currency}</td>
              <td>{transaction.jurisdiction}</td>
              <td>{transaction.riskScore}</td>
              <td><span className={`transaction-status transaction-status-${String(transaction.status).toLowerCase()}`}>{transaction.status}</span></td>
            </tr>
          )) : (
            <tr className="transactions-empty-row">
              <td colSpan={columns.length}>No transactions yet</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default function TransactionsPage() {
  const { transactions, metrics } = useTransactionStream()
  const [period, setPeriod] = useState('Last 24h')
  const [query, setQuery] = useState('')
  const [segment, setSegment] = useState('All')
  const [paused, setPaused] = useState(false)
  const tableScrollRef = useRef(null)
  const reviewCount = transactions.filter((transaction) => transaction.status === 'Review').length
  const flaggedCount = transactions.filter((transaction) => transaction.status === 'Flagged').length
  const rows = transactions.filter((transaction) => {
    if (segment !== 'All' && transaction.status !== segment) return false
    const searchable = [transaction.hash, transaction.account, transaction.jurisdiction].join(' ').toLowerCase()
    return searchable.includes(query.trim().toLowerCase())
  }).slice(-100)

  function jumpToLatest() {
    setPaused(false)
    const scrollArea = tableScrollRef.current
    if (scrollArea) scrollArea.scrollTop = scrollArea.scrollHeight
  }

  useEffect(() => {
    if (!paused && tableScrollRef.current) {
      tableScrollRef.current.scrollTop = tableScrollRef.current.scrollHeight
    }
  }, [paused, transactions])

  return (
    <div className="transactions-page">
      <PageHeader period={period} onPeriodChange={setPeriod} throughput={metrics.throughput} paused={paused} />
      <section className="transactions-metrics-grid" aria-label="Transaction metrics">
        <MetricCard
          title="Transaction volume (24h)"
          subtitle="Aggregate processed counter"
          value={formatCount(metrics.volume)}
          detail={`${metrics.volumeChange >= 0 ? '+' : ''}${metrics.volumeChange.toFixed(1)}% vs mean`}
          series={seriesFor(transactions, period, 'volume')}
          period={period}
          yTicks={[{ value: 0, label: '0' }, { value: 5000, label: '5k' }, { value: 10000, label: '10k' }, { value: 15000, label: '15k' }]}
          maxValue={15000}
          emptyMarker={12000}
          chartTitle="Transaction volume over time"
        />
        <MetricCard
          title="Fraud rate (%) (24h)"
          subtitle={`Threshold benchmark: ${metrics.threshold.toFixed(2)}%`}
          value={`${metrics.fraudAverage.toFixed(2)}% avg`}
          detail={`Peak ${metrics.fraudPeak.toFixed(2)}%`}
          series={seriesFor(transactions, period, 'fraud')}
          period={period}
          yTicks={[{ value: 0, label: '0.0%' }, { value: 0.2, label: '0.2%' }, { value: 0.4, label: '0.4%' }, { value: 0.6, label: '0.6%' }]}
          maxValue={0.6}
          threshold={metrics.threshold}
          emptyMarker={0}
          chartTitle="Fraud rate over time"
        />
      </section>
      <FilterBar transactions={transactions} query={query} onQueryChange={setQuery} segment={segment} onSegmentChange={setSegment} filteredRows={rows} />
      <FeedStatusBar paused={paused} onTogglePaused={() => setPaused((value) => !value)} onJumpToLatest={jumpToLatest} />
      <TransactionTable rows={rows} scrollRef={tableScrollRef} />
      <span className="sr-only" aria-live="polite">{reviewCount} review transactions and {flaggedCount} flagged transactions</span>
    </div>
  )
}