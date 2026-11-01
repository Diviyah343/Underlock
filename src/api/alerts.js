import { apiRequest } from './client.js'

export function getAlerts(
  { status = 'open', page = 1, pageSize = 100 } = {},
  options = {},
) {
  const query = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  })
  if (status) query.set('status', status)
  return apiRequest(`/alerts?${query.toString()}`, options)
}

export function getAlert(alertId, options = {}) {
  return apiRequest(`/alerts/${encodeURIComponent(alertId)}`, options)
}

export function submitAlertDecision(alertId, decision, note) {
  return apiRequest(`/alerts/${encodeURIComponent(alertId)}/decision`, {
    method: 'POST',
    body: { decision, note: note || null },
  })
}
