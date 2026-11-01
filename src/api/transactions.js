import { apiRequest, buildApiUrl, createAuthHeaders, redirectToLogin } from './client.js'

function buildTransactionQuery({ search = '', status } = {}) {
  const query = new URLSearchParams()
  if (search.trim()) query.set('search', search.trim())
  if (status) query.set('status', status)
  return query
}

export function getTransactions({ search = '', status, limit = 100, offset = 0 } = {}, options = {}) {
  const query = buildTransactionQuery({ search, status })
  query.set('limit', String(limit))
  query.set('offset', String(offset))
  return apiRequest(`/transactions?${query.toString()}`, options)
}

export function getTransactionMetrics(range = '24h', fraud_rate_threshold = 0.05, options = {}) {
  const query = new URLSearchParams({
    range,
    fraud_rate_threshold: String(fraud_rate_threshold),
  })
  return apiRequest(`/metrics/transactions?${query.toString()}`, options)
}

export async function exportTransactions({ search = '', status } = {}) {
  const query = buildTransactionQuery({ search, status })
  const queryString = query.toString()
  const path = queryString ? `/transactions/export.csv?${queryString}` : '/transactions/export.csv'
  const response = await fetch(buildApiUrl(path), {
    method: 'GET',
    headers: createAuthHeaders({ Accept: 'text/csv' }),
  })

  if (response.status === 401) redirectToLogin()
  if (!response.ok) {
    const body = await response.text()
    throw new Error(body || `CSV export failed with status ${response.status}`)
  }

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'transactions.csv'
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
