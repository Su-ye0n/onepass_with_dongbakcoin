import assert from 'node:assert/strict'
import test from 'node:test'
import { api, ApiError } from '../lib/api.ts'
import { resolveApiRoute } from '../lib/api/route-policy.ts'
import { proxyApiRequest } from '../lib/api/server-client.ts'
import { resolveQrMerchant } from '../lib/qr-payment.ts'

test('allows frontend user, wallet, card, benefit, merchant, and payment API operations', () => {
  const cases = [
    [['v1', 'health', 'db'], 'GET'],
    [['v1', 'auth', 'register'], 'POST'],
    [['v1', 'auth', 'login'], 'POST'],
    [['v1', 'auth', 'logout'], 'POST'],
    [['v1', 'cards', 'products'], 'GET'],
    [['v1', 'users', 'USER_001', 'cards'], 'GET'],
    [['v1', 'users', 'USER_001', 'identity-cards'], 'GET'],
    [['v1', 'users', 'USER_001', 'cards'], 'POST'],
    [['v1', 'users', 'USER_001', 'cards', 'CARD_001'], 'DELETE'],
    [['v1', 'users', 'USER_001', 'profile'], 'GET'],
    [['v1', 'users', 'USER_001', 'profile'], 'PUT'],
    [['v1', 'users', 'USER_001', 'wallet'], 'GET'],
    [['v1', 'users', 'USER_001', 'wallet', 'top-ups'], 'POST'],
    [['v1', 'merchants'], 'GET'],
    [['v1', 'benefits', 'products', 'PRODUCT_001'], 'GET'],
    [['v1', 'payments', 'recommend'], 'POST'],
    [['v1', 'payments'], 'POST'],
    [['v1', 'users', 'USER_001', 'payments'], 'GET'],
  ]

  for (const [path, method] of cases) {
    assert.equal(
      resolveApiRoute(path, method, new URLSearchParams()).kind,
      'allowed',
      `${method} /${path.join('/')}`,
    )
  }
})

test('resolves only known merchants from supported demo QR payloads', () => {
  const merchants = [
    { merchant_id: 'MERCHANT_001', merchant_name: '테스트 가맹점', industry_code: 'CAFE' },
  ]
  assert.equal(resolveQrMerchant('MERCHANT_001', merchants), merchants[0])
  assert.equal(
    resolveQrMerchant('dongbaek://pay?merchant_id=MERCHANT_001', merchants),
    merchants[0],
  )
  assert.equal(
    resolveQrMerchant('{"merchant_id":"MERCHANT_001"}', merchants),
    merchants[0],
  )
  assert.equal(resolveQrMerchant('MERCHANT_UNKNOWN', merchants), null)
  assert.equal(resolveQrMerchant('https://example.com/?merchant_id=MERCHANT_001', merchants), null)
})

test('forwards a validated bearer token to the authenticated backend', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com'
  let upstreamInit
  t.mock.method(globalThis, 'fetch', async (_url, init) => {
    upstreamInit = init
    return Response.json({ user_id: 'USR_001' })
  })

  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/users/USR_001/profile', {
      headers: { Authorization: 'Bearer abcdefghijklmnopqrstuvwxyz_123456' },
    }),
    ['v1', 'users', 'USR_001', 'profile'],
  )

  assert.equal(response.status, 200)
  assert.equal(
    upstreamInit.headers.Authorization,
    'Bearer abcdefghijklmnopqrstuvwxyz_123456',
  )
})

test('sends logout as an empty JSON POST for the proxy', async (t) => {
  let upstreamInit
  t.mock.method(globalThis, 'fetch', async (_url, init) => {
    upstreamInit = init
    return new Response(null, { status: 204 })
  })

  await api.logout()
  assert.equal(upstreamInit.method, 'POST')
  assert.equal(upstreamInit.headers['Content-Type'], 'application/json')
  assert.equal(upstreamInit.body, '{}')
})

test('rejects malformed bearer tokens before contacting the backend', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com'
  const upstream = t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ ok: true }),
  )
  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/auth/logout', {
      method: 'POST',
      headers: {
        Authorization: 'Basic not-a-token',
        'Content-Type': 'application/json',
      },
      body: '{}',
    }),
    ['v1', 'auth', 'logout'],
  )
  assert.equal(response.status, 400)
  assert.equal(upstream.mock.callCount(), 0)
})

test('forwards allowlisted profile updates as JSON PUT requests', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com'
  let upstreamUrl
  let upstreamInit
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    upstreamUrl = String(url)
    upstreamInit = init
    return Response.json({ user_id: 'USER_001', display_name: '김개미' })
  })

  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/users/USER_001/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: '김개미' }),
    }),
    ['v1', 'users', 'USER_001', 'profile'],
  )

  assert.equal(response.status, 200)
  assert.equal(upstreamUrl, 'https://backend.example.com/api/v1/users/USER_001/profile')
  assert.equal(upstreamInit.method, 'PUT')
  assert.deepEqual(JSON.parse(upstreamInit.body), { display_name: '김개미' })
})

test('rejects unknown paths, methods, and unsafe path segments', () => {
  assert.equal(
    resolveApiRoute(
      ['v1', 'admin', 'users'],
      'GET',
      new URLSearchParams(),
    ).kind,
    'not-found',
  )
  assert.equal(
    resolveApiRoute(
      ['v1', 'payments'],
      'GET',
      new URLSearchParams(),
    ).kind,
    'method-not-allowed',
  )
  assert.equal(
    resolveApiRoute(
      ['v1', 'users', '..', 'cards'],
      'GET',
      new URLSearchParams(),
    ).kind,
    'not-found',
  )
  assert.equal(
    resolveApiRoute(
      ['v1', 'users', 'USER/OTHER', 'cards'],
      'GET',
      new URLSearchParams(),
    ).kind,
    'not-found',
  )
})

test('restricts and validates merchant pagination query parameters', () => {
  assert.equal(
    resolveApiRoute(
      ['v1', 'merchants'],
      'GET',
      new URLSearchParams('limit=100&offset=0'),
    ).kind,
    'allowed',
  )
  for (const query of ['limit=0', 'limit=501', 'offset=-1', 'limit=10&limit=20', 'url=https://example.com']) {
    assert.equal(
      resolveApiRoute(
        ['v1', 'merchants'],
        'GET',
        new URLSearchParams(query),
      ).kind,
      'invalid-query',
      query,
    )
  }
})

test('proxies only to the configured API base and disables caching', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com/api/v1'
  let upstreamUrl
  let upstreamInit
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    upstreamUrl = String(url)
    upstreamInit = init
    return Response.json([{ product_id: 'P1' }])
  })

  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/cards/products'),
    ['v1', 'cards', 'products'],
  )

  assert.equal(response.status, 200)
  assert.equal(upstreamUrl, 'https://backend.example.com/api/v1/cards/products')
  assert.equal(upstreamInit.cache, 'no-store')
  assert.equal(response.headers.get('cache-control'), 'no-store')
  assert.deepEqual(await response.json(), [{ product_id: 'P1' }])
})

test('defaults to the fixed local FastAPI URL only in development', async (t) => {
  delete process.env.BACKEND_URL
  process.env.NODE_ENV = 'development'
  let upstreamUrl
  t.mock.method(globalThis, 'fetch', async (url) => {
    upstreamUrl = String(url)
    return Response.json({ status: 'ok' })
  })

  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/health/db'),
    ['v1', 'health', 'db'],
  )

  assert.equal(response.status, 200)
  assert.equal(upstreamUrl, 'http://127.0.0.1:8000/api/v1/health/db')
})

test('adds the API prefix to a configured Render origin', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com'
  process.env.NODE_ENV = 'test'
  let upstreamUrl
  t.mock.method(globalThis, 'fetch', async (url) => {
    upstreamUrl = String(url)
    return Response.json({ status: 'ok' })
  })

  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/health/db'),
    ['v1', 'health', 'db'],
  )

  assert.equal(response.status, 200)
  assert.equal(upstreamUrl, 'https://backend.example.com/api/v1/health/db')
})

test('requires BACKEND_URL in production without exposing configuration', async (t) => {
  delete process.env.BACKEND_URL
  process.env.NODE_ENV = 'production'
  const upstream = t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ ok: true }),
  )

  const response = await proxyApiRequest(
    new Request('https://frontend.example.com/api/v1/health/db'),
    ['v1', 'health', 'db'],
  )

  assert.equal(response.status, 500)
  assert.equal(upstream.mock.callCount(), 0)
})

test('preserves backend client errors and masks server error details', async (t) => {
  process.env.NODE_ENV = 'test'
  process.env.BACKEND_URL = 'https://backend.example.com/api/v1'
  t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: 'validation failed' }, { status: 422 }),
  )

  const clientError = await proxyApiRequest(
    new Request('http://localhost/api/v1/payments/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount_won: -1 }),
    }),
    ['v1', 'payments', 'recommend'],
  )
  assert.equal(clientError.status, 422)
  assert.deepEqual(await clientError.json(), { detail: 'validation failed' })

  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: 'database password must not be exposed' }, { status: 503 }),
  )
  const serverError = await proxyApiRequest(
    new Request('http://localhost/api/v1/payments/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount_won: 100 }),
    }),
    ['v1', 'payments', 'recommend'],
  )
  assert.equal(serverError.status, 503)
  assert.deepEqual(await serverError.json(), {
    detail: '백엔드에서 오류가 발생했습니다.',
  })
})

test('rejects invalid JSON, oversized bodies, and untrusted routes before fetch', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com/api/v1'
  const upstream = t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ ok: true }),
  )

  const invalidJson = await proxyApiRequest(
    new Request('http://localhost/api/v1/payments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{',
    }),
    ['v1', 'payments'],
  )
  assert.equal(invalidJson.status, 400)

  const oversized = await proxyApiRequest(
    new Request('http://localhost/api/v1/payments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: 'x'.repeat(17_000) }),
    }),
    ['v1', 'payments'],
  )
  assert.equal(oversized.status, 413)

  const untrusted = await proxyApiRequest(
    new Request('http://localhost/api/v1/proxy?url=https://example.com'),
    ['v1', 'proxy'],
  )
  assert.equal(untrusted.status, 404)
  assert.equal(upstream.mock.callCount(), 0)
})

test('rejects unexpected backend content types and invalid backend URLs', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com/api/v1'
  t.mock.method(globalThis, 'fetch', async () =>
    new Response('<html>not json</html>', {
      headers: { 'Content-Type': 'text/html' },
    }),
  )

  const badResponse = await proxyApiRequest(
    new Request('http://localhost/api/v1/cards/products'),
    ['v1', 'cards', 'products'],
  )
  assert.equal(badResponse.status, 502)

  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () =>
    new Response('{', {
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  const invalidJson = await proxyApiRequest(
    new Request('http://localhost/api/v1/cards/products'),
    ['v1', 'cards', 'products'],
  )
  assert.equal(invalidJson.status, 502)

  process.env.BACKEND_URL = 'https://backend.example.com/unexpected'
  const badConfiguration = await proxyApiRequest(
    new Request('http://localhost/api/v1/cards/products'),
    ['v1', 'cards', 'products'],
  )
  assert.equal(badConfiguration.status, 500)
})

test('reports backend network failures without treating them as success', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com/api/v1'
  t.mock.method(globalThis, 'fetch', async () => {
    throw new TypeError('connection refused')
  })

  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/cards/products'),
    ['v1', 'cards', 'products'],
  )
  assert.equal(response.status, 502)
  assert.deepEqual(await response.json(), {
    detail: '백엔드 API에 연결할 수 없습니다.',
  })
})

test('browser API client uses same-origin uncached requests and reports failures', async (t) => {
  let requestUrl
  let requestInit
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    requestUrl = String(url)
    requestInit = init
    return Response.json([{ product_id: 'P1' }])
  })

  assert.deepEqual(await api.getProducts(), [{ product_id: 'P1' }])
  assert.equal(requestUrl, '/api/v1/cards/products')
  assert.equal(requestInit.cache, 'no-store')

  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: 'not found' }, { status: 404 }),
  )
  await assert.rejects(api.getProducts(), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 404)
    assert.equal(error.kind, 'http')
    assert.equal(error.message, 'not found')
    return true
  })

  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => new Response('{'))
  await assert.rejects(api.getProducts(), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.kind, 'invalid-response')
    return true
  })

  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => {
    throw new TypeError('network failure')
  })
  await assert.rejects(api.getProducts(), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.kind, 'network')
    return true
  })
})

test('returns a gateway timeout when the backend request times out', async (t) => {
  process.env.BACKEND_URL = 'https://backend.example.com/api/v1'
  t.mock.method(globalThis, 'fetch', async (_url, init) =>
    new Promise((resolve, reject) => {
      init.signal.addEventListener(
        'abort',
        () => reject(new DOMException('Timed out', 'TimeoutError')),
        { once: true },
      )
    }),
  )

  const response = await proxyApiRequest(
    new Request('http://localhost/api/v1/cards/products'),
    ['v1', 'cards', 'products'],
  )

  assert.equal(response.status, 504)
})
