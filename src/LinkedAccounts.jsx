import { useInvestigations } from './Investigations.jsx'

const EMPTY_STATE_CASE_ID = 'INV-2024-0892'

export function useLinkedAccounts(caseId) {
  const { cases } = useInvestigations()
  const caseRecord = cases.find((caseItem) => caseItem.id === caseId)
    ?? (caseId === EMPTY_STATE_CASE_ID ? { id: caseId } : null)

  // TODO: load the case graph and connection records from the investigations API.
  const nodes = caseRecord?.linkedAccounts?.nodes ?? []
  const connections = caseRecord?.linkedAccounts?.connections ?? []

  return { caseRecord, nodes, connections }
}

function PageHeader({ caseId, onBackToList, onOpenCase, connections }) {
  function exportConnections() {
    const columns = ['Account', 'Relationship', 'Shared signal', 'Linked transactions', 'Last activity']
    const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const rows = connections.map((connection) => [
      connection.account ?? connection.label,
      connection.relationship,
      connection.sharedSignal,
      connection.linkedTransactions,
      connection.lastActivity,
    ])
    const csv = [columns, ...rows].map((row) => row.map(escape).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${caseId}-linked-accounts.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <header className="linked-accounts-header">
      <nav aria-label="Breadcrumb" className="linked-accounts-breadcrumb">
        <a href="/investigations" onClick={(event) => { event.preventDefault(); onBackToList() }}>Investigations</a>
        <span aria-hidden="true">/</span>
        <a href={`/investigations/${encodeURIComponent(caseId)}`} onClick={(event) => { event.preventDefault(); onOpenCase(caseId) }}>{caseId}</a>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Linked accounts</span>
      </nav>
      <button className="linked-accounts-export" type="button" onClick={exportConnections} disabled={!connections.length}>
        Export
      </button>
    </header>
  )
}

function GraphLegend({ nodeCount }) {
  return (
    <div className="linked-accounts-legend">
      <div className="linked-accounts-legend-items" aria-label="Connection types">
        <span className="linked-accounts-legend-item"><span className="linked-accounts-line linked-accounts-line-transfer" />Fund transfer</span>
        <span className="linked-accounts-legend-item"><span className="linked-accounts-line linked-accounts-line-ip" />Shared IP</span>
        <span className="linked-accounts-legend-item"><span className="linked-accounts-line linked-accounts-line-device" />Shared device</span>
      </div>
      <span className="linked-accounts-node-count">{nodeCount} Connected Nodes</span>
    </div>
  )
}

function NetworkGraph({ caseId, nodes, connections }) {
  const width = 1000
  const height = 420
  const center = { x: width / 2, y: height / 2 }
  const radius = Math.min(width * 0.32, height * 0.38)
  const positionedNodes = nodes.map((node, index) => {
    const angle = ((Math.PI * 2) / Math.max(nodes.length, 1)) * index - Math.PI / 2
    return {
      ...node,
      x: Number.isFinite(node.x) ? node.x : center.x + Math.cos(angle) * radius,
      y: Number.isFinite(node.y) ? node.y : center.y + Math.sin(angle) * radius,
    }
  })
  const positions = new Map(positionedNodes.map((node) => [node.id, node]))

  return (
    <svg className="linked-accounts-graph" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${nodes.length} connected accounts for case ${caseId}`}>
      {connections.map((connection, index) => {
        const source = positions.get(connection.source)
        const target = positions.get(connection.target)
        if (!source || !target) return null
        return (
          <line
            key={connection.id ?? `${connection.source}-${connection.target}-${index}`}
            className={`linked-accounts-edge linked-accounts-edge-${connection.type ?? 'transfer'}`}
            x1={source.x}
            y1={source.y}
            x2={target.x}
            y2={target.y}
          />
        )
      })}
      {positionedNodes.map((node) => (
        <g key={node.id} className="linked-accounts-node">
          <circle cx={node.x} cy={node.y} r="24" />
          <text x={node.x} y={node.y + 42} textAnchor="middle">{node.label ?? node.account ?? node.id}</text>
        </g>
      ))}
    </svg>
  )
}

function ConnectionList({ connections }) {
  return (
    <section className="linked-accounts-list-card" aria-labelledby="connection-list-title">
      <h2 id="connection-list-title">CONNECTION LIST</h2>
      <div className="linked-accounts-list-scroll">
        <table className="linked-accounts-table">
          <thead>
            <tr>
              <th scope="col">ACCOUNT</th>
              <th scope="col">RELATIONSHIP</th>
              <th scope="col">SHARED SIGNAL</th>
              <th scope="col">LINKED TRANSACTIONS</th>
              <th scope="col">LAST ACTIVITY</th>
            </tr>
          </thead>
          <tbody>
            {connections.length ? connections.map((connection, index) => (
              <tr key={connection.id ?? `${connection.account}-${index}`}>
                <td>{connection.account ?? connection.label}</td>
                <td>{connection.relationship ?? '--'}</td>
                <td>{connection.sharedSignal ?? '--'}</td>
                <td>{connection.linkedTransactions ?? 0}</td>
                <td>{connection.lastActivity ?? '--'}</td>
              </tr>
            )) : (
              <tr className="linked-accounts-empty-row"><td colSpan={5}>No linked accounts</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function LinkedAccountsPage({ caseId, onBackToList, onOpenCase }) {
  const { caseRecord, nodes, connections } = useLinkedAccounts(caseId)
  const displayCaseId = caseRecord?.id ?? caseId

  return (
    <main className="transactions-page linked-accounts-page">
      <PageHeader caseId={displayCaseId} onBackToList={onBackToList} onOpenCase={onOpenCase} connections={connections} />
      <div className="linked-accounts-header-rule" />
      {caseRecord ? (
        <>
          <section className="linked-accounts-graph-card" aria-label="Account relationship graph">
            <GraphLegend nodeCount={nodes.length} />
            <NetworkGraph caseId={displayCaseId} nodes={nodes} connections={connections} />
          </section>
          <ConnectionList connections={connections} />
        </>
      ) : (
        <p className="linked-accounts-not-found" role="status">Case not found</p>
      )}
    </main>
  )
}