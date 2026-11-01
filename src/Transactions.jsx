import { useEffect, useRef, useState } from 'react'
import { exportTransactions, getTransactionMetrics, getTransactions } from './api/transactions.js'
import { openEventStream } from './api/sse.js'

const WINDOWS = {
  'Last 24h': { apiRange: '24h', label: 'Last 24h' },
  '1h': { apiRange: '1h', label: '1h' },
  Live: { apiRange: 'live', label: 'Live' },
}

function displayStatus(status) {
  return status ? `${status[0].toUpperCase()}${status.slice(1)}` : 'Unknown'
}

function chartLabels(series) {
  if (series.length <= 7) {
    return series.map((point, index) => index === series.length - 1
      ? 'NOW'
      : new Date(point.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
  }
  const labels = []
  for (let index = 0; index < 7; index += 1) {
    const pointIndex = Math.round((index * (series.length - 1)) / 6)
    labels.push(index === 6
      ? 'NOW'
      : new Date(series[pointIndex].timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
  }
  return labels
}

function volumeAxis(maxValue) {
  const safeMax = maxValue > 0 ? maxValue : 1
  const step = safeMax / 3
  return {
    maxValue: safeMax,
    yTicks: Array.from({ length: 4 }, (_, index) => {
      const value = step * index
      return {
        value,
        label: value >= 1000000
          ? `${(value / 1000000).toFixed(1)}m`
          : value >= 1000
            ? `${(value / 1000).toFixed(1)}k`
            : value.toFixed(0),
      }
    }),
  }
}

function fraudAxis(maxValue) {
  const safeMax = maxValue > 0 ? maxValue : 1
  const step = safeMax / 3
  return {
    maxValue: safeMax,
    yTicks: Array.from({ length: 4 }, (_, index) => {
      const value = step * index
      return { value, label: `${value.toFixed(2)}%` }
    }),
  }
}

function mapTransaction(transaction) {
  return {
    ...transaction,
    display_status: displayStatus(transaction.status),
  }
}

export function useTransactionStream({ period, query, status, paused }) {
  const [transactions, setTransactions] = useState([])
  const [statusCounts, setStatusCounts] = useState({ cleared: 0, review: 0, flagged: 0 })
  const [metrics, setMetrics] = useState({
    throughput_tx_s: 0,
    total_count: 0,
    volume_series: [],
    fraud_rate_series: [],
    fraud_rate_threshold: 0.05,
  })
  const [error, setError] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState(query)
  const refreshTransactionsRef = useRef(() => {})
  const refreshMetricsRef = useRef(() => {})
  const refreshTimerRef = useRef(null)
  const pausedRef = useRef(paused)

  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 300)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const controller = new AbortController()
    refreshTransactionsRef.current = async () => {
      const page = await getTransactions({
        search: debouncedQuery,
        status,
        limit: 100,
        offset: 0,
      }, { signal: controller.signal })
      setTransactions(page.items.map(mapTransaction))
      setStatusCounts(page.status_counts)
      setError('')
    }

    void refreshTransactionsRef.current().catch((loadError) => {
      if (loadError.name !== 'AbortError') setError(loadError.message || 'Unable to load transactions.')
    })

    return () => controller.abort()
  }, [debouncedQuery, status])

  useEffect(() => {
    const controller = new AbortController()
    refreshMetricsRef.current = async () => {
      const result = await getTransactionMetrics(WINDOWS[period].apiRange, 0.05, {
        signal: controller.signal,
      })
      setMetrics(result)
    }
    void refreshMetricsRef.current().catch((loadError) => {
      if (loadError.name !== 'AbortError') setError(loadError.message || 'Unable to load transaction metrics.')
    })
    return () => controller.abort()
  }, [period])

  useEffect(() => {
    const controller = new AbortController()
    const stream = openEventStream('/transactions/stream', {
      onEvent(event) {
        if (event.event !== 'transaction') return
        if (pausedRef.current) return
        window.clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = window.setTimeout(() => {
          void refreshTransactionsRef.current().catch((loadError) => {
            if (loadError.name !== 'AbortError') setError(loadError.message || 'Unable to refresh transactions.')
          })
          void refreshMetricsRef.current().catch((loadError) => {
            if (loadError.name !== 'AbortError') setError(loadError.message || 'Unable to refresh metrics.')
          })
        }, 250)
      },
      onError(streamError) {
        setError(streamError.message || 'Transaction stream disconnected.')
      },
      signal: controller.signal,
    })
    return () => {
      stream.close()
      controller.abort()
      window.clearTimeout(refreshTimerRef.current)
    }
  }, [])

  const fraudRates = metrics.fraud_rate_series.map((point) => point.fraud_rate * 100)
  const volumeValues = metrics.volume_series.map((point) => Number(point.volume))

  return {
    transactions,
    statusCounts,
    metrics: {
      throughput: metrics.throughput_tx_s,
      volume: metrics.total_count,
      volumeSeries: volumeValues,
      volumeLabels: chartLabels(metrics.volume_series),
      volumePeak: Math.max(0, ...volumeValues),
      fraudAverage: fraudRates.length
        ? fraudRates.reduce((total, value) => total + value, 0) / fraudRates.length
        : 0,
      fraudPeak: Math.max(0, ...fraudRates),
      fraudSeries: fraudRates,
      fraudLabels: chartLabels(metrics.fraud_rate_series),
      threshold: metrics.fraud_rate_threshold * 100,
      error,
    },
    refreshTransactions: () => refreshTransactionsRef.current(),
  }
}

function formatCount(value) {
  const padded = String(value).padStart(8, '0')
  return `${padded.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} tx`
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
        <span className="transactions-throughput">Throughput: {Number(throughput).toFixed(2)} tx/s</span>
        <span className="transactions-header-divider" aria-hidden="true" />
        <div className="transactions-segmented" aria-label="Chart time range">
          {Object.keys(WINDOWS).map((option) => (
            <button key={option} type="button" aria-pressed={period === option} onClick={() => onPeriodChange(option)}>
              {WINDOWS[option].label}
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
  const chartMax = maxValue > 0 ? maxValue : 1
  const points = values.map((value, index) => ({
    x: plot.left + (plotWidth * index) / Math.max(values.length - 1, 1),
    y: plot.bottom - (Math.min(value, chartMax) / chartMax) * plotHeight,
  }))
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  const markerY = plot.bottom - (Math.min(emptyMarker, chartMax) / chartMax) * plotHeight
  const thresholdY = plot.bottom - (Math.min(threshold, chartMax) / chartMax) * plotHeight

  return (
    <svg className="transactions-chart-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={title}>
      {yTicks.map((tick) => {
        const y = plot.bottom - (tick.value / chartMax) * plotHeight
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

function MetricCard({ title, subtitle, value, detail, series, labels, yTicks, maxValue, threshold, emptyMarker, chartTitle }) {
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
        labels={labels}
        yTicks={yTicks}
        maxValue={maxValue}
        threshold={threshold}
        emptyMarker={emptyMarker}
      />
    </article>
  )
}

function FilterBar({ query, onQueryChange, segment, onSegmentChange, statusCounts, onExport }) {
  const counts = {
    all: Object.values(statusCounts).reduce((total, count) => total + count, 0),
    cleared: statusCounts.cleared ?? 0,
    review: statusCounts.review ?? 0,
    flagged: statusCounts.flagged ?? 0,
  }
  const tabs = [
    { label: `All (${counts.all})`, value: 'All' },
    { label: `Cleared (${counts.cleared})`, value: 'cleared' },
    { label: `Review (${counts.review})`, value: 'review' },
    { label: `Flagged (${counts.flagged})`, value: 'flagged' },
  ]

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
        <button className="transactions-export-button" type="button" onClick={onExport}>Export CSV</button>
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
            <tr key={transaction.id ?? index} className={`transaction-row-${transaction.status}`}>
              <td>{new Date(transaction.occurred_at).toLocaleString()}</td>
              <td>{transaction.tx_hash}</td>
              <td>{transaction.account_id}</td>
              <td>{transaction.amount} {transaction.currency}</td>
              <td>{transaction.jurisdiction}</td>
              <td>{transaction.risk_score ?? '—'}</td>
              <td><span className={`transaction-status transaction-status-${transaction.status}`}>{transaction.display_status}</span></td>
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
  const [period, setPeriod] = useState('Last 24h')
  const [query, setQuery] = useState('')
  const [segment, setSegment] = useState('All')
  const [paused, setPaused] = useState(false)
  const [exportError, setExportError] = useState('')
  const tableScrollRef = useRef(null)
  const selectedStatus = segment === 'All' ? undefined : segment
  const {
    transactions,
    statusCounts,
    metrics,
    refreshTransactions,
  } = useTransactionStream({ period, query, status: selectedStatus, paused })
  const rows = transactions

  function jumpToLatest() {
    setPaused(false)
    void refreshTransactions().catch((error) => setExportError(error.message || 'Unable to refresh transactions.'))
    const scrollArea = tableScrollRef.current
    if (scrollArea) scrollArea.scrollTop = 0
  }

  function togglePaused() {
    if (paused) {
      void refreshTransactions().catch((error) => {
        setExportError(error.message || 'Unable to refresh transactions.')
      })
    }
    setPaused(!paused)
  }

  useEffect(() => {
    if (!paused && tableScrollRef.current) {
      tableScrollRef.current.scrollTop = 0
    }
  }, [paused, transactions])

  async function handleExport() {
    setExportError('')
    try {
      await exportTransactions({ search: query, status: selectedStatus })
    } catch (error) {
      setExportError(error.message || 'Unable to export transactions.')
    }
  }

  const volumeChart = volumeAxis(metrics.volumePeak * 1.1)
  const fraudChart = fraudAxis(Math.max(metrics.fraudPeak, metrics.threshold) * 1.1)

  return (
    <div className="transactions-page">
      <PageHeader period={period} onPeriodChange={setPeriod} throughput={metrics.throughput} paused={paused} />
      <section className="transactions-metrics-grid" aria-label="Transaction metrics">
        <MetricCard
          title={`Transaction volume (${WINDOWS[period].label})`}
          subtitle="Aggregate transaction amount"
          value={formatCount(metrics.volume)}
          detail={`Peak ${metrics.volumePeak.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          series={metrics.volumeSeries}
          labels={metrics.volumeLabels}
          yTicks={volumeChart.yTicks}
          maxValue={volumeChart.maxValue}
          emptyMarker={metrics.volumePeak}
          chartTitle="Transaction volume over time"
        />
        <MetricCard
          title={`Fraud rate (%) (${WINDOWS[period].label})`}
          subtitle={`Threshold benchmark: ${metrics.threshold.toFixed(2)}%`}
          value={`${metrics.fraudAverage.toFixed(2)}% avg`}
          detail={`Peak ${metrics.fraudPeak.toFixed(2)}%`}
          series={metrics.fraudSeries}
          labels={metrics.fraudLabels}
          yTicks={fraudChart.yTicks}
          maxValue={fraudChart.maxValue}
          threshold={metrics.threshold}
          emptyMarker={0}
          chartTitle="Fraud rate over time"
        />
      </section>
      {metrics.error && <p className="px-[12px] py-[6px] font-mono text-[9px] text-[#9b3f3f]" role="alert">{metrics.error}</p>}
      {exportError && <p className="px-[12px] py-[6px] font-mono text-[9px] text-[#9b3f3f]" role="alert">{exportError}</p>}
      <FilterBar
        query={query}
        onQueryChange={setQuery}
        segment={segment}
        onSegmentChange={setSegment}
        statusCounts={statusCounts}
        onExport={() => void handleExport()}
      />
      <FeedStatusBar paused={paused} onTogglePaused={togglePaused} onJumpToLatest={jumpToLatest} />
      <TransactionTable rows={rows} scrollRef={tableScrollRef} />
      <span className="sr-only" aria-live="polite">{statusCounts.review} review transactions and {statusCounts.flagged} flagged transactions</span>
    </div>
  )
}