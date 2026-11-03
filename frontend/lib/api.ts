const API_BASE_PATH = 'https://onepass-with-dongbakcoin.onrender.com/api/v1'
const AUTH_SESSION_STORAGE_KEY = 'onepass-auth-session'

export type AuthSession = {
  access_token: string
  expires_at: string
  user: {
    user_id: string
    username: string
  }
}

export type CardProduct = {
  product_id: string
  product_name: string
  issuer: string | null
  card_type: string | null
  product_status: string | null
  terms_version?: string | null
  source_status?: string | null
  source_ref?: string | null
}

export type UserCard = {
  user_card_id: string
  user_id: string
  product_id: string
  db_wallet_id?: string | null
  linked_account_id?: string | null
  card_status: string | null
  credit_limit_won: number | null
  default_preference_rank: number | null
  expires_at?: string | null
  registered_ref?: string | null
  active_from?: string | null
  active_to?: string | null
}

export type Merchant = {
  merchant_id: string
  merchant_name: string | null
  industry_code: string
  source_merchant_id?: string | null
  dongbaek_status?: string | null
  sales_band?: string | null
  sales_band_basis_at?: string | null
  is_good_price_shop?: boolean | null
  is_dbplus_shop?: boolean | null
  is_qr_merchant?: boolean | null
  dbplus_discount_rate?: number | string | null
  region_code?: string | null
  source_status?: string | null
}

export type BenefitRule = {
  rule_id: string
  product_id: string
  benefit_name: string | null
  benefit_type: string | null
  rate: string | null
  fixed_amount_won: number | null
  per_tx_cap_won: number | null
  monthly_cap_won: number | null
  monthly_count_cap: number | null
  min_amount_won?: number | null
  shared_cap_group?: string | null
  day_condition?: string | null
  perf_threshold_won?: number | null
  perf_basis_code?: string | null
  reward_unit?: string | null
  stack_rule?: string | null
  payment_channel_required?: string | null
  rounding_mode?: string | null
  valid_from?: string | null
  valid_to?: string | null
  source_status?: string | null
}

export type CategoryPriority = {
  priority_id: string
  user_id: string
  user_category_code: string
  user_card_id: string
  priority_group: number | null
}

export type PaymentCandidate = {
  user_card_id: string
  product_id: string | null
  product_name: string | null
  expected_benefit_won: number
  eligible: boolean
  reason: string | null
}

export type PaymentRecommendation = {
  user_id: string
  merchant_id: string
  amount_won: number
  recommended_user_card_id: string | null
  expected_benefit_won: number
  candidates: PaymentCandidate[]
}

export type PaymentRecord = {
  tx_id: string
  user_id: string
  user_card_id: string
  merchant_id: string
  amount_won: number
  approval_status: string
  event_at: string
  merchant_name: string | null
  product_name: string | null
  awarded_benefit_won: number | null
  source_mode: string | null
  event_note: string | null
}

export type UserProfile = {
  user_id: string
  display_name: string | null
  student_card_id: string | null
  university: string | null
  department: string | null
  phone_number: string | null
  address: string | null
  source_mode: string
}

export type UserIdentityCard = {
  identity_card_id: string
  user_id: string
  card_type: 'CIVIC' | 'STUDENT' | string
  issuer_name: string
  title: string
  holder_name: string
  subtitle: string
  status: string
  service_summary: string
  credential_label: string
  source_mode: string
  created_at: string
}

export type WalletAccount = {
  wallet_id: string
  charge_won: number
  cashback_won: number
  policy_support_won: number
  balance_won: number
}

export type WalletBalance = {
  user_id: string
  balance_won: number
  wallets: WalletAccount[]
}

export type WalletTopUp = {
  tx_id: string
  request_id: string
  user_id: string
  wallet_id: string
  amount_won: number
  balance_won: number
  charge_won: number
  cashback_won: number
  policy_support_won: number
  approval_status: string
  source_mode: string
  event_at: string
}

export class ApiError extends Error {
  readonly status: number | null
  readonly kind: 'network' | 'timeout' | 'http' | 'invalid-response'

  constructor(
    message: string,
    status: number | null,
    kind: 'network' | 'timeout' | 'http' | 'invalid-response',
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.kind = kind
  }
}

export function readAuthSession(): AuthSession | null {
  if (typeof window === 'undefined') return null
  const stored = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY)
  if (!stored) return null
  try {
    const session: unknown = JSON.parse(stored)
    if (
      typeof session === 'object' &&
      session !== null &&
      'access_token' in session &&
      typeof session.access_token === 'string' &&
      'expires_at' in session &&
      typeof session.expires_at === 'string' &&
      'user' in session &&
      typeof session.user === 'object' &&
      session.user !== null &&
      'user_id' in session.user &&
      typeof session.user.user_id === 'string' &&
      'username' in session.user &&
      typeof session.user.username === 'string' &&
      Date.parse(session.expires_at) > Date.now()
    ) {
      return session as AuthSession
    }
  } catch {
    window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
    return null
  }
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
  return null
}

export function writeAuthSession(session: AuthSession | null): void {
  if (typeof window === 'undefined') return
  if (session) {
    window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session))
  } else {
    window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
  }
}

type RequestOptions = {
  signal?: AbortSignal
}

async function request<T>(
  path: string,
  init?: RequestInit,
  options?: RequestOptions,
): Promise<T> {
  const timeoutSignal = AbortSignal.timeout(15_000)
  const signal = options?.signal
    ? AbortSignal.any([options.signal, timeoutSignal])
    : timeoutSignal

  let response: Response
  try {
    const session = readAuthSession()
    response = await fetch(`${API_BASE_PATH}${path}`, {
      ...init,
      cache: 'no-store',
      signal,
      headers: {
        ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch (cause) {
    if (options?.signal?.aborted) throw cause
    if (timeoutSignal.aborted) {
      throw new ApiError('API 요청 시간이 초과되었습니다. 다시 시도해 주세요.', 504, 'timeout')
    }
    throw new ApiError(
      '백엔드 API에 연결할 수 없습니다. 서버 상태를 확인해 주세요.',
      null,
      'network',
    )
  }

  if (
    response.status === 401 &&
    !path.startsWith('/auth/') &&
    typeof window !== 'undefined'
  ) {
    window.dispatchEvent(new Event('onepass:auth-expired'))
  }

  let text: string
  try {
    text = await response.text()
  } catch {
    if (options?.signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    if (timeoutSignal.aborted) {
      throw new ApiError('API 응답 시간이 초과되었습니다. 다시 시도해 주세요.', 504, 'timeout')
    }
    throw new ApiError(
      '백엔드 응답을 읽을 수 없습니다. 다시 시도해 주세요.',
      response.status,
      'network',
    )
  }

  if (!response.ok) {
    let message = `API 요청에 실패했습니다. (${response.status})`
    try {
      const body: unknown = JSON.parse(text)
      if (
        typeof body === 'object' &&
        body !== null &&
        'detail' in body &&
        typeof body.detail === 'string'
      ) {
        message = body.detail
      }
    } catch {
      // Keep the HTTP status when an error response is not JSON.
    }
    throw new ApiError(message, response.status, 'http')
  }

  if (response.status === 204) return undefined as T
  if (!text.trim()) {
    throw new ApiError(
      '백엔드가 비어 있는 응답을 반환했습니다.',
      response.status,
      'invalid-response',
    )
  }

  try {
    return JSON.parse(text) as T
  } catch {
    throw new ApiError(
      '백엔드가 올바르지 않은 JSON 응답을 반환했습니다.',
      response.status,
      'invalid-response',
    )
  }
}

export const api = {
  checkDatabase: (options?: RequestOptions) =>
    request<{ status: string; database: string }>('/health/db', undefined, options),
  register: (payload: { username: string; password: string }) =>
    request<AuthSession>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  login: (payload: { username: string; password: string }) =>
    request<AuthSession>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  logout: () =>
    request<void>('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  getProfile: (userId: string, options?: RequestOptions) =>
    request<UserProfile>(
      `/users/${encodeURIComponent(userId)}/profile`,
      undefined,
      options,
    ),
  getIdentityCards: (userId: string, options?: RequestOptions) =>
    request<UserIdentityCard[]>(
      `/users/${encodeURIComponent(userId)}/identity-cards`,
      undefined,
      options,
    ),
  updateProfile: (
    userId: string,
    payload: {
      display_name: string
      student_card_id: string | null
      university: string | null
      department: string | null
      phone_number: string | null
      address: string | null
    },
  ) =>
    request<UserProfile>(`/users/${encodeURIComponent(userId)}/profile`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getWalletBalance: (userId: string, options?: RequestOptions) =>
    request<WalletBalance>(
      `/users/${encodeURIComponent(userId)}/wallet`,
      undefined,
      options,
    ),
  createWalletTopUp: (
    userId: string,
    payload: { request_id: string; amount_won: number; wallet_id?: string },
  ) =>
    request<WalletTopUp>(
      `/users/${encodeURIComponent(userId)}/wallet/top-ups`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  getProducts: (options?: RequestOptions) =>
    request<CardProduct[]>('/cards/products', undefined, options),
  getProduct: (productId: string, options?: RequestOptions) =>
    request<CardProduct>(
      `/cards/products/${encodeURIComponent(productId)}`,
      undefined,
      options,
    ),
  getUserCards: (userId: string, options?: RequestOptions) =>
    request<UserCard[]>(
      `/users/${encodeURIComponent(userId)}/cards`,
      undefined,
      options,
    ),
  getUserCard: (
    userId: string,
    userCardId: string,
    options?: RequestOptions,
  ) =>
    request<UserCard>(
      `/users/${encodeURIComponent(userId)}/cards/${encodeURIComponent(userCardId)}`,
      undefined,
      options,
    ),
  getCardPriorities: (userId: string, options?: RequestOptions) =>
    request<UserCard[]>(
      `/users/${encodeURIComponent(userId)}/cards/priorities`,
      undefined,
      options,
    ),
  updateCardPriorities: (
    userId: string,
    cards: { user_card_id: string; priority: number }[],
  ) =>
    request<UserCard[]>(
      `/users/${encodeURIComponent(userId)}/cards/priorities`,
      {
        method: 'PUT',
        body: JSON.stringify({ cards }),
      },
    ),
  getCategoryPriorities: (userId: string, options?: RequestOptions) =>
    request<CategoryPriority[]>(
      `/users/${encodeURIComponent(userId)}/category-priorities`,
      undefined,
      options,
    ),
  updateCategoryPriorities: (
    userId: string,
    priorities: {
      user_category_code: string
      user_card_id: string
      priority_group: number
    }[],
  ) =>
    request<CategoryPriority[]>(
      `/users/${encodeURIComponent(userId)}/category-priorities`,
      {
        method: 'PUT',
        body: JSON.stringify({ priorities }),
      },
    ),
  getMerchants: (options?: RequestOptions) =>
    request<Merchant[]>('/merchants?limit=100', undefined, options),
  getMerchant: (merchantId: string, options?: RequestOptions) =>
    request<Merchant>(
      `/merchants/${encodeURIComponent(merchantId)}`,
      undefined,
      options,
    ),
  getBenefits: (productId: string, options?: RequestOptions) =>
    request<BenefitRule[]>(
      `/benefits/products/${encodeURIComponent(productId)}`,
      undefined,
      options,
    ),
  getBenefitRule: (ruleId: string, options?: RequestOptions) =>
    request<BenefitRule>(
      `/benefits/${encodeURIComponent(ruleId)}`,
      undefined,
      options,
    ),
  getPaymentHistory: (userId: string, options?: RequestOptions) =>
    request<{ payments: PaymentRecord[] }>(
      `/users/${encodeURIComponent(userId)}/payments`,
      undefined,
      options,
    ),
  getPaymentDetail: (transactionId: string, options?: RequestOptions) =>
    request<PaymentRecord>(
      `/payments/${encodeURIComponent(transactionId)}`,
      undefined,
      options,
    ),
  recommendPayment: (
    payload: {
      user_id: string
      merchant_id: string
      amount_won: number
    },
    options?: RequestOptions,
  ) =>
    request<PaymentRecommendation>(
      '/payments/recommend',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      options,
    ),
  createPayment: (payload: {
    request_id: string
    user_id: string
    user_card_id: string
    merchant_id: string
    amount_won: number
  }) =>
    request<{ tx_id: string; approval_status: string; event_at: string }>(
      '/payments',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  addUserCard: (userId: string, productId: string) =>
    request<UserCard>(`/users/${encodeURIComponent(userId)}/cards`, {
      method: 'POST',
      body: JSON.stringify({ product_id: productId }),
    }),
  removeUserCard: (userId: string, userCardId: string) =>
    request<void>(
      `/users/${encodeURIComponent(userId)}/cards/${encodeURIComponent(userCardId)}`,
      { method: 'DELETE' },
    ),
}
