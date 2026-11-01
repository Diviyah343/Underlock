const configuredApiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const API_BASE_URL = configuredApiUrl.replace(/\/+$/, '')

const TOKEN_STORAGE_KEY = 'underlock.access_token'
const ANALYST_ID_STORAGE_KEY = 'underlock.analyst_id'
let accessToken = readStoredToken()

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

function readStoredToken() {
  if (typeof window === 'undefined') return null
  return window.sessionStorage.getItem(TOKEN_STORAGE_KEY)
}

export function getAccessToken() {
  return accessToken
}

export function getAnalystId() {
  if (typeof window === 'undefined') return null
  return window.sessionStorage.getItem(ANALYST_ID_STORAGE_KEY)
}

export function setAccessToken(token) {
  if (typeof token !== 'string' || token.length === 0) {
    throw new TypeError('An access token must be a non-empty string')
  }
  accessToken = token
  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
  }
}

export function clearAccessToken() {
  accessToken = null
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(TOKEN_STORAGE_KEY)
    window.sessionStorage.removeItem(ANALYST_ID_STORAGE_KEY)
  }
}

function setAnalystId(analystId) {
  if (typeof analystId !== 'string' || analystId.length === 0) {
    throw new TypeError('Login response did not include analyst_id')
  }
  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(ANALYST_ID_STORAGE_KEY, analystId)
  }
}

export function buildApiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}

export function createAuthHeaders(headers) {
  const result = new Headers(headers)
  result.set('Authorization', accessToken ? `Bearer ${accessToken}` : '')
  return result
}

export function redirectToLogin() {
  clearAccessToken()
  if (typeof window !== 'undefined') {
    window.location.replace('/?login=required')
  }
}

async function readErrorBody(response) {
  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()
  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(text)
    } catch {
      return text || null
    }
  }
  return text || null
}

export async function apiRequest(path, {
  redirectOnUnauthorized = true,
  ...options
} = {}) {
  const headers = createAuthHeaders(options.headers)
  const requestOptions = { ...options, headers }

  if (
    requestOptions.body !== undefined
    && typeof requestOptions.body !== 'string'
    && !(typeof FormData !== 'undefined' && requestOptions.body instanceof FormData)
    && !(typeof Blob !== 'undefined' && requestOptions.body instanceof Blob)
  ) {
    headers.set('Content-Type', 'application/json')
    requestOptions.body = JSON.stringify(requestOptions.body)
  }

  const response = await fetch(buildApiUrl(path), requestOptions)
  if (response.status === 401 && redirectOnUnauthorized) {
    redirectToLogin()
  }
  if (!response.ok) {
    const body = await readErrorBody(response)
    const detail = body && typeof body === 'object' ? body.detail : null
    throw new ApiError(
      typeof detail === 'string' ? detail : `API request failed with status ${response.status}`,
      response.status,
      body,
    )
  }
  if (response.status === 204) return null
  if (response.headers.get('content-length') === '0') return null
  return response.json()
}

export async function login(analyst_code, password) {
  const result = await apiRequest('/auth/login', {
    method: 'POST',
    body: { analyst_code, password },
    redirectOnUnauthorized: false,
  })
  if (typeof result?.access_token !== 'string') {
    throw new TypeError('Login response did not include access_token')
  }
  setAnalystId(result.analyst_id)
  setAccessToken(result.access_token)
  return result
}

export async function logout() {
  try {
    return await apiRequest('/auth/logout', { method: 'POST' })
  } finally {
    clearAccessToken()
  }
}
