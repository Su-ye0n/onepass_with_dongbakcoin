import type { Merchant } from './api'

function merchantIdFromValue(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null

  if (trimmed.startsWith('{')) {
    try {
      const payload: unknown = JSON.parse(trimmed)
      if (
        typeof payload === 'object' &&
        payload !== null &&
        'merchant_id' in payload &&
        typeof payload.merchant_id === 'string'
      ) {
        return payload.merchant_id
      }
    } catch {
      return null
    }
  }

  try {
    const url = new URL(trimmed)
    if (url.protocol === 'dongbaek:' && url.hostname === 'pay') {
      return url.searchParams.get('merchant_id')
    }
    return null
  } catch {
    return trimmed
  }
}

export function resolveQrMerchant(
  value: string,
  merchants: readonly Merchant[],
): Merchant | null {
  const merchantId = merchantIdFromValue(value)
  if (!merchantId) return null
  return merchants.find((merchant) => merchant.merchant_id === merchantId) ?? null
}
