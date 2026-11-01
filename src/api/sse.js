import {
  ApiError,
  buildApiUrl,
  createAuthHeaders,
  redirectToLogin,
} from './client.js'

const DEFAULT_RETRY_DELAY_MS = 1000
const MAX_RETRY_DELAY_MS = 30000

function dispatchSseFrame(frame, onEvent) {
  let event = 'message'
  let id
  const data = []

  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    const value = separator === -1 ? '' : line.slice(separator + 1).replace(/^ /, '')

    if (field === 'event') event = value
    if (field === 'id' && !value.includes('\0')) id = value
    if (field === 'data') data.push(value)
  }

  if (data.length > 0) onEvent({ event, data: data.join('\n'), id })
}

async function consumeEventStream(body, onEvent, onConnected) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let separatorIndex
      while ((separatorIndex = buffer.search(/(?:\r\n|\r|\n)(?:\r\n|\r|\n)/)) !== -1) {
        const frame = buffer.slice(0, separatorIndex)
        const separator = buffer.slice(separatorIndex).match(/^(?:\r\n|\r|\n)(?:\r\n|\r|\n)/)[0]
        buffer = buffer.slice(separatorIndex + separator.length)
        dispatchSseFrame(frame, onEvent)
        onConnected()
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) dispatchSseFrame(buffer, onEvent)
  } finally {
    reader.releaseLock()
  }
}

export function openEventStream(path, {
  onEvent = () => {},
  onError = () => {},
  signal,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  maxRetryDelayMs = MAX_RETRY_DELAY_MS,
} = {}) {
  let closed = Boolean(signal?.aborted)
  let retryAttempt = 0
  let retryTimer
  let activeController

  const close = () => {
    closed = true
    clearTimeout(retryTimer)
    activeController?.abort()
  }

  const scheduleReconnect = () => {
    if (closed) return
    const delay = Math.min(retryDelayMs * (2 ** retryAttempt), maxRetryDelayMs)
    retryAttempt += 1
    retryTimer = setTimeout(connect, delay)
  }

  const connect = async () => {
    if (closed) return
    const controller = new AbortController()
    activeController = controller
    const abortFromCaller = () => controller.abort(signal.reason)
    signal?.addEventListener('abort', abortFromCaller, { once: true })

    try {
      const response = await fetch(buildApiUrl(path), {
        method: 'GET',
        headers: createAuthHeaders({ Accept: 'text/event-stream' }),
        signal: controller.signal,
      })

      if (response.status === 401) {
        closed = true
        clearTimeout(retryTimer)
        redirectToLogin()
        return
      }
      if (!response.ok) {
        const body = await response.text()
        throw new ApiError(
          `Event stream request failed with status ${response.status}`,
          response.status,
          body || null,
        )
      }
      if (!response.body) {
        throw new Error('Event stream response did not include a readable body')
      }

      await consumeEventStream(response.body, onEvent, () => {
        retryAttempt = 0
      })
    } catch (error) {
      if (!closed && !signal?.aborted && !controller.signal.aborted) {
        onError(error)
      }
    } finally {
      signal?.removeEventListener('abort', abortFromCaller)
      if (!closed && !signal?.aborted && !controller.signal.aborted) {
        scheduleReconnect()
      }
    }
  }

  if (!closed) void connect()
  signal?.addEventListener('abort', close, { once: true })

  return {
    close() {
      signal?.removeEventListener('abort', close)
      close()
    },
  }
}
