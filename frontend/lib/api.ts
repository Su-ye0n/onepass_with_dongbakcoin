const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000/api/v1'
).replace(/\/$/, '')

export const DEMO_USER_ID = process.env.NEXT_PUBLIC_DEMO_USER_ID ?? 'USER_001'

export type CardProduct = {
  product_id: string
  product_name: string
  issuer: string | null
  card_type: string | null
  product_status: string | null
}

export type UserCard = {
  user_card_id: string
  user_id: string
  product_id: string
  card_status: string | null
  default_preference_rank: number | null
}

export type Merchant = {
  merchant_id: string
  merchant_name: string | null
  industry_code: string
}

export type BenefitRule = {
  rule_id: string
  product_id: string
  benefit_name: string | null
  benefit_type: string | null
  rate: number | null
  fixed_amount_won: number | null
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new Error('백엔드 API에 연결할 수 없습니다. 서버 주소와 실행 상태를 확인해 주세요.')
  }

  if (!response.ok) {
    let message = `API 요청에 실패했습니다. (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  getProducts: () => request<CardProduct[]>('/cards/products'),
  getUserCards: (userId: string) =>
    request<UserCard[]>(`/users/${encodeURIComponent(userId)}/cards`),
  getMerchants: () => request<Merchant[]>('/merchants?limit=100'),
  getBenefits: (productId: string) =>
    request<BenefitRule[]>(`/benefits/products/${encodeURIComponent(productId)}`),
  getPaymentHistory: (userId: string) =>
    request<{ payments: PaymentRecord[] }>(
      `/users/${encodeURIComponent(userId)}/payments`,
    ),
  recommendPayment: (payload: {
    user_id: string
    merchant_id: string
    amount_won: number
  }) =>
    request<PaymentRecommendation>('/payments/recommend', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
