import { apiRequest } from './client.js'

export function getInvestigations(
  { status, search = '', page = 1, pageSize = 25 } = {},
  options = {},
) {
  const query = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  })
  if (status) query.set('status', status)
  if (search.trim()) query.set('search', search.trim())
  return apiRequest(`/investigations?${query.toString()}`, options)
}

export function getInvestigationStats(options = {}) {
  return apiRequest('/investigations/stats', options)
}

export function createInvestigation({ title, alert_ids }, options = {}) {
  return apiRequest('/investigations', {
    ...options,
    method: 'POST',
    body: { title, alert_ids },
  })
}

export function getInvestigationGraph(investigationId, options = {}) {
  return apiRequest(`/investigations/${encodeURIComponent(investigationId)}/graph`, options)
}
