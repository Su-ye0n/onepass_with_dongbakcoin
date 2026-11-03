import { resolveApiRoute } from './route-policy.ts'

const BACKEND_TIMEOUT_MS = 10_000
const MAX_REQUEST_BODY_BYTES = 16 * 1024
const MAX_RESPONSE_BODY_BYTES = 2 * 1024 * 1024

class BackendConfigurationError extends Error {}

function getBackendBaseUrl(): URL {
  const configuredUrl =
    process.env.BACKEND_URL?.trim() ||
    (process.env.NODE_ENV === 'development'
      ? 'http://127.0.0.1:8000/api/v1'
      : undefined)
  if (!configuredUrl) {
    throw new BackendConfigurationError('BACKEND_URL is not configured.')
  }

  let url: URL
  try {
    url = new URL(configuredUrl)
  } catch {
    throw new BackendConfigurationError('BACKEND_URL must be an absolute URL.')
  }

  const isLoopback =
    url.hostname === 'localhost' || url.hostname === '127.0.0.1'
  const configuredPath = url.pathname.replace(/\/+$/, '')
  if (
    (url.protocol !== 'https:' && !(url.protocol === 'http:' && isLoopback)) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (configuredPath !== '' && configuredPath !== '/api/v1')
  ) {
    throw new BackendConfigurationError(
      'BACKEND_URL must use HTTPS and point to a trusted API origin.',
    )
  }

  return new URL(`${url.origin}/api/v1/`)
}

function jsonResponse(
  status: number,
  detail: string,
  extraHeaders?: HeadersInit,
): Response {
  return Response.json(
    { detail },
    {
      status,
      headers: {
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
        ...extraHeaders,
      },
    },
  )
}

async function readJsonBody(request: Request): Promise<string | Response> {
  const contentType = request.headers.get('content-type') ?? ''
  if (!/^application\/json(?:\s*;|$)/i.test(contentType)) {
    return jsonResponse(415, '요청은 JSON 형식이어야 합니다.')
  }

  const contentLength = Number(request.headers.get('content-length'))
  if (Number.isFinite(contentLength) && contentLength > MAX_REQUEST_BODY_BYTES) {
    return jsonResponse(413, '요청 본문이 허용 크기를 초과했습니다.')
  }

  if (!request.body) {
    return jsonResponse(400, 'JSON 요청 본문이 필요합니다.')
  }

  const reader = request.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    size += value.byteLength
    if (size > MAX_REQUEST_BODY_BYTES) {
      await reader.cancel()
      return jsonResponse(413, '요청 본문이 허용 크기를 초과했습니다.')
    }
    chunks.push(value)
  }

  const body = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    body.set(chunk, offset)
    offset += chunk.byteLength
  }

  let text: string
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(body)
    JSON.parse(text)
  } catch {
    return jsonResponse(400, '올바른 JSON 요청 본문이 필요합니다.')
  }

  return text
}

async function readUpstreamBody(
  upstream: Response,
): Promise<Uint8Array | null> {
  if (!upstream.body) return new Uint8Array()

  const contentLength = Number(upstream.headers.get('content-length'))
  if (
    Number.isFinite(contentLength) &&
    contentLength > MAX_RESPONSE_BODY_BYTES
  ) {
    await upstream.body.cancel()
    return null
  }

  const reader = upstream.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    size += value.byteLength
    if (size > MAX_RESPONSE_BODY_BYTES) {
      await reader.cancel()
      return null
    }
    chunks.push(value)
  }

  const body = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    body.set(chunk, offset)
    offset += chunk.byteLength
  }
  return body
}

export async function proxyApiRequest(
  request: Request,
  path: readonly string[],
): Promise<Response> {
  const policy = resolveApiRoute(
    path,
    request.method,
    new URL(request.url).searchParams,
  )

  if (policy.kind === 'not-found') {
    return jsonResponse(404, '허용되지 않은 API 경로입니다.')
  }
  if (policy.kind === 'method-not-allowed') {
    return jsonResponse(405, '허용되지 않은 HTTP 메서드입니다.', {
      Allow: policy.allow.join(', '),
    })
  }
  if (policy.kind === 'invalid-query') {
    return jsonResponse(400, '허용되지 않은 조회 조건입니다.')
  }

  let body: string | undefined
  if (request.method === 'POST' || request.method === 'PUT') {
    const parsedBody = await readJsonBody(request)
    if (parsedBody instanceof Response) return parsedBody
    body = parsedBody
  }

  let backendUrl: URL
  try {
    backendUrl = getBackendBaseUrl()
  } catch (cause) {
    if (cause instanceof BackendConfigurationError) {
      return jsonResponse(500, '백엔드 주소 설정을 확인해 주세요.')
    }
    throw cause
  }

  const encodedPath = path
    .slice(1)
    .map((segment) => encodeURIComponent(segment))
    .join('/')
  const targetUrl = new URL(encodedPath, backendUrl)
  for (const key of policy.queryKeys) {
    const value = new URL(request.url).searchParams.get(key)
    if (value !== null) targetUrl.searchParams.set(key, value)
  }

  const timeoutSignal = AbortSignal.timeout(BACKEND_TIMEOUT_MS)
  const signal = AbortSignal.any([request.signal, timeoutSignal])
  const authorization = request.headers.get('authorization')
  if (
    authorization !== null &&
    !/^Bearer [A-Za-z0-9_-]{20,128}$/.test(authorization)
  ) {
    return jsonResponse(400, '로그인 인증 형식이 올바르지 않습니다.')
  }

  let upstream: Response
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers: {
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(authorization === null ? {} : { Authorization: authorization }),
      },
      body,
      cache: 'no-store',
      redirect: 'manual',
      signal,
    })
  } catch {
    if (timeoutSignal.aborted && !request.signal.aborted) {
      return jsonResponse(504, '백엔드 응답 시간이 초과되었습니다.')
    }
    if (request.signal.aborted) {
      return new Response(null, { status: 499 })
    }
    return jsonResponse(502, '백엔드 API에 연결할 수 없습니다.')
  }

  const headers = new Headers({
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  })
  const contentType = upstream.headers.get('content-type')
  if (contentType) headers.set('Content-Type', contentType)

  if (upstream.status >= 300 && upstream.status < 400) {
    return jsonResponse(502, '백엔드가 예상하지 못한 리다이렉트를 반환했습니다.')
  }
  if (upstream.status >= 500) {
    return jsonResponse(upstream.status, '백엔드에서 오류가 발생했습니다.')
  }
  if (upstream.status !== 204 && upstream.ok && !contentType?.includes('application/json')) {
    return jsonResponse(502, '백엔드 응답 형식이 올바르지 않습니다.')
  }

  let responseBody: Uint8Array | null = null
  if (upstream.status !== 204) {
    try {
      responseBody = await readUpstreamBody(upstream)
    } catch {
      if (timeoutSignal.aborted && !request.signal.aborted) {
        return jsonResponse(504, '백엔드 응답 시간이 초과되었습니다.')
      }
      if (request.signal.aborted) {
        return new Response(null, { status: 499 })
      }
      return jsonResponse(502, '백엔드 응답을 읽을 수 없습니다.')
    }
    if (responseBody === null) {
      return jsonResponse(502, '백엔드 응답 크기가 허용 범위를 초과했습니다.')
    }

    if (
      upstream.ok &&
      contentType?.includes('application/json')
    ) {
      try {
        JSON.parse(new TextDecoder().decode(responseBody))
      } catch {
        return jsonResponse(502, '백엔드가 올바르지 않은 JSON 응답을 반환했습니다.')
      }
    }
  }

  return new Response(responseBody, {
    status: upstream.status,
    headers,
  })
}
