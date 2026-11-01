import { useEffect, useMemo, useState } from 'react'
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from 'd3-force'
import { getInvestigationGraph } from './api/investigations.js'

export function useLinkedAccounts(caseId) {
  const [graph, setGraph] = useState({ nodes: [], edges: [], connections: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    getInvestigationGraph(caseId, { signal: controller.signal })
      .then(setGraph)
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message || 'Unable to load linked accounts.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [caseId])

  return { ...graph, loading, error }
}

function PageHeader({ caseId, onBackToList, onOpenCase, connections }) {
  function exportConnections() {
    const columns = ['Accounts', 'Relationship', 'Shared signal', 'Linked transactions', 'Last activity']
    const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const rows = connections.map((connection) => connection.csvRow)
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

function NetworkGraph({ caseId, nodes, connections, onSelectNode, selectedNodeId }) {
  const width = 1000
  const height = 420
  const [positionedNodes, setPositionedNodes] = useState([])

  useEffect(() => {
    const simulationNodes = nodes.map((node, index) => {
      const angle = ((Math.PI * 2) / Math.max(nodes.length, 1)) * index
      const radius = Math.min(width, height) * 0.28
      return {
        ...node,
        x: width / 2 + Math.cos(angle) * radius,
        y: height / 2 + Math.sin(angle) * radius,
      }
    })
    const simulationEdges = connections.map((connection) => ({ ...connection }))
    const simulation = forceSimulation(simulationNodes)
      .force('link', forceLink(simulationEdges).id((node) => node.id).distance(145).strength(0.75))
      .force('charge', forceManyBody().strength(-420))
      .force('center', forceCenter(width / 2, height / 2))
      .force('collide', forceCollide(48))
      .on('tick', () => setPositionedNodes(simulationNodes.map((node) => ({ ...node }))))

    setPositionedNodes(simulationNodes.map((node) => ({ ...node })))
    return () => simulation.stop()
  }, [nodes, connections])

  const positions = useMemo(() => new Map(positionedNodes.map((node) => [node.id, node])), [positionedNodes])

  return (
    <svg className="linked-accounts-graph" viewBox={`0 0 ${width} ${height}`} role="group" aria-label={`${nodes.length} connected accounts for case ${caseId}`}>
      {connections.map((connection, index) => {
        const source = positions.get(typeof connection.source === 'string' ? connection.source : connection.source.id)
        const target = positions.get(typeof connection.target === 'string' ? connection.target : connection.target.id)
        if (!source || !target) return null
        return (
          <line
            key={`${connection.source}-${connection.target}-${connection.type}-${index}`}
            className={`linked-accounts-edge linked-accounts-edge-${connection.type}`}
            x1={source.x}
            y1={source.y}
            x2={target.x}
            y2={target.y}
          />
        )
      })}
      {positionedNodes.map((node) => (
        <g
          key={node.id}
          className={`linked-accounts-node${selectedNodeId === node.id ? ' linked-accounts-node-selected' : ''}`}
          role="button"
          tabIndex={0}
          aria-label={`Show account details for ${node.name || node.external_ref}`}
          aria-pressed={selectedNodeId === node.id}
          onClick={() => onSelectNode(node.id)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              onSelectNode(node.id)
            }
          }}
        >
          <circle cx={node.x} cy={node.y} r="24" />
          <text x={node.x} y={node.y + 42} textAnchor="middle">{node.external_ref}</text>
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
              <tr key={`${connection.account}-${connection.relationship}-${index}`}>
                <td>{connection.account}</td>
                <td>{connection.relationship}</td>
                <td>{connection.sharedSignal}</td>
                <td>{connection.linkedTransactions}</td>
                <td>{connection.lastActivity}</td>
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

function formatConnections(nodes, graphConnections) {
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  return graphConnections.map((connection) => {
    const source = nodesById.get(typeof connection.source === 'string' ? connection.source : connection.source.id)
    const target = nodesById.get(typeof connection.target === 'string' ? connection.target : connection.target.id)
    const relationship = {
      fund_transfer: 'Fund transfer',
      shared_ip: 'Shared IP',
      shared_device: 'Shared device',
    }[connection.type] ?? connection.type
    const sharedSignal = connection.shared_value
      ?? (connection.amount == null ? '--' : `$${connection.amount}`)
    const lastActivity = connection.last_seen_at
      ? new Date(connection.last_seen_at).toLocaleString()
      : '--'
    const account = `${source?.external_ref ?? 'Unknown'} ↔ ${target?.external_ref ?? 'Unknown'}`
    return {
      account,
      relationship,
      sharedSignal,
      linkedTransactions: connection.transaction_count ?? 0,
      lastActivity,
      csvRow: [account, relationship, sharedSignal, connection.transaction_count ?? 0, lastActivity],
    }
  })
}

function GraphContent({ caseId, nodes, edges, graphConnections }) {
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const connections = graphConnections.length ? graphConnections : edges
  const connectionRows = formatConnections(nodes, connections)
  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  const selectedNode = nodesById.get(selectedNodeId)

  return (
    <div className="linked-accounts-page linked-accounts-graph-panel">
      <div className="linked-accounts-header-rule" />
      <section className="linked-accounts-graph-card" aria-label="Account relationship graph">
        <GraphLegend nodeCount={nodes.length} />
        <NetworkGraph
          caseId={caseId}
          nodes={nodes}
          connections={connections}
          onSelectNode={setSelectedNodeId}
          selectedNodeId={selectedNodeId}
        />
      </section>
      {selectedNode && (
        <section className="linked-account-node-details" aria-live="polite">
          <h2>ACCOUNT DETAILS</h2>
          <dl>
            <div><dt>Account</dt><dd>{selectedNode.name || selectedNode.external_ref}</dd></div>
            <div><dt>Reference</dt><dd>{selectedNode.external_ref}</dd></div>
            <div><dt>Account ID</dt><dd>{selectedNode.id}</dd></div>
          </dl>
        </section>
      )}
      <ConnectionList connections={connectionRows} />
    </div>
  )
}

export function InvestigationGraphPanel({ caseId }) {
  const { nodes, edges, connections, loading, error } = useLinkedAccounts(caseId)
  if (loading) return <p className="linked-accounts-not-found" role="status">Loading linked accounts…</p>
  if (error) return <p className="linked-accounts-not-found" role="alert">{error}</p>
  return <GraphContent caseId={caseId} nodes={nodes} edges={edges} graphConnections={connections} />
}

export default function LinkedAccountsPage({ caseId, onBackToList, onOpenCase }) {
  const { nodes, edges, connections: graphConnections, loading, error } = useLinkedAccounts(caseId)
  const connections = graphConnections.length ? graphConnections : edges
  const connectionRows = formatConnections(nodes, connections)

  return (
    <main className="transactions-page linked-accounts-page">
      <PageHeader caseId={caseId} onBackToList={onBackToList} onOpenCase={onOpenCase} connections={connectionRows} />
      {loading ? (
        <p className="linked-accounts-not-found" role="status">Loading linked accounts…</p>
      ) : error ? (
        <p className="linked-accounts-not-found" role="alert">{error}</p>
      ) : (
        <GraphContent caseId={caseId} nodes={nodes} edges={edges} graphConnections={graphConnections} />
      )}
    </main>
  )
}