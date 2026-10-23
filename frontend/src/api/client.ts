const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, body.detail || '请求失败')
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export type StreamEvent =
  | { type: 'status'; step: string; label: string }
  | { type: 'delta'; content: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

export async function* streamApi(
  path: string,
  body: unknown,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new ApiError(response.status, payload.detail || '请求失败')
  }
  if (!response.body) throw new Error('浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line) as StreamEvent
    }
    if (done) {
      if (buffer.trim()) yield JSON.parse(buffer) as StreamEvent
      break
    }
  }
}

export async function subscribeEvents(
  after: number,
  signal: AbortSignal,
  onEvent: (event: import('../types').DomainEvent) => void,
): Promise<number> {
  const response = await fetch(`${API_BASE}/events/stream?after=${after}`, {
    credentials: 'include',
    signal,
    headers: { Accept: 'text/event-stream' },
  })
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, '实时事件连接失败')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let cursor = after
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const data = frame.split('\n')
        .find(line => line.startsWith('data: '))?.slice(6)
      if (!data) continue
      const event = JSON.parse(data) as import('../types').DomainEvent
      cursor = event.id
      onEvent(event)
    }
    if (done) return cursor
  }
}
