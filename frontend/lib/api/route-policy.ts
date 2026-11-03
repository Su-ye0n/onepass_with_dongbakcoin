export type ApiMethod = 'GET' | 'POST' | 'PUT' | 'DELETE'

type RouteRule = {
  methods: readonly ApiMethod[]
  segments: readonly string[]
  query?: Readonly<Record<string, { min: number; max: number }>>
}

const routeRules: readonly RouteRule[] = [
  { methods: ['GET'], segments: ['v1', 'health', 'db'] },
  { methods: ['POST'], segments: ['v1', 'auth', 'register'] },
  { methods: ['POST'], segments: ['v1', 'auth', 'login'] },
  { methods: ['POST'], segments: ['v1', 'auth', 'logout'] },
  { methods: ['GET'], segments: ['v1', 'cards', 'products'] },
  {
    methods: ['GET'],
    segments: ['v1', 'users', ':userId', 'cards'],
  },
  {
    methods: ['GET'],
    segments: ['v1', 'users', ':userId', 'identity-cards'],
  },
  {
    methods: ['GET', 'PUT'],
    segments: ['v1', 'users', ':userId', 'profile'],
  },
  {
    methods: ['GET'],
    segments: ['v1', 'users', ':userId', 'wallet'],
  },
  {
    methods: ['POST'],
    segments: ['v1', 'users', ':userId', 'wallet', 'top-ups'],
  },
  {
    methods: ['POST'],
    segments: ['v1', 'users', ':userId', 'cards'],
  },
  {
    methods: ['DELETE'],
    segments: ['v1', 'users', ':userId', 'cards', ':userCardId'],
  },
  {
    methods: ['GET'],
    segments: ['v1', 'merchants'],
    query: {
      limit: { min: 1, max: 500 },
      offset: { min: 0, max: Number.MAX_SAFE_INTEGER },
    },
  },
  {
    methods: ['GET'],
    segments: ['v1', 'benefits', 'products', ':productId'],
  },
  {
    methods: ['POST'],
    segments: ['v1', 'payments', 'recommend'],
  },
  { methods: ['POST'], segments: ['v1', 'payments'] },
  {
    methods: ['GET'],
    segments: ['v1', 'users', ':userId', 'payments'],
  },
]

export type RoutePolicyResult =
  | { kind: 'allowed'; queryKeys: readonly string[] }
  | { kind: 'not-found' }
  | { kind: 'method-not-allowed'; allow: readonly ApiMethod[] }
  | { kind: 'invalid-query' }

function matchesPath(rule: RouteRule, path: readonly string[]): boolean {
  return (
    rule.segments.length === path.length &&
    rule.segments.every((segment, index) => {
      const value = path[index]
      if (segment.startsWith(':')) {
        return (
          value.length > 0 &&
          value !== '.' &&
          value !== '..' &&
          !/[\\/\u0000-\u001f\u007f]/.test(value)
        )
      }
      return segment === value
    })
  )
}

export function resolveApiRoute(
  path: readonly string[],
  method: string,
  searchParams: URLSearchParams,
): RoutePolicyResult {
  const matchingRules = routeRules.filter((rule) => matchesPath(rule, path))
  if (!matchingRules.length) return { kind: 'not-found' }

  const allowedMethods = [
    ...new Set(matchingRules.flatMap((rule) => rule.methods)),
  ]
  if (!allowedMethods.includes(method as ApiMethod)) {
    return { kind: 'method-not-allowed', allow: allowedMethods }
  }

  const rule = matchingRules.find((candidate) =>
    candidate.methods.includes(method as ApiMethod),
  )
  if (!rule) return { kind: 'method-not-allowed', allow: allowedMethods }

  const queryKeys = Object.keys(rule.query ?? {})
  for (const key of searchParams.keys()) {
    if (!queryKeys.includes(key)) return { kind: 'invalid-query' }
  }

  for (const key of queryKeys) {
    const values = searchParams.getAll(key)
    if (values.length > 1) return { kind: 'invalid-query' }
    if (!values.length) continue

    const value = values[0]
    const range = rule.query?.[key]
    const number = Number(value)
    if (
      !range ||
      !/^(0|[1-9]\d*)$/.test(value) ||
      !Number.isSafeInteger(number) ||
      number < range.min ||
      number > range.max
    ) {
      return { kind: 'invalid-query' }
    }
  }

  return { kind: 'allowed', queryKeys }
}
