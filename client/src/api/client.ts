const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  })

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = data?.detail ?? JSON.stringify(data)
    throw new Error(message || `Request failed with ${response.status}`)
  }
  return data as T
}

export type BankAccount = {
  id: number
  account_holder_name: string
  bank_name: string
  ifsc: string
  account_number_last4: string
  is_active: boolean
}

export type Merchant = {
  id: number
  name: string
  bank_accounts: BankAccount[]
}

export type Balance = {
  merchant_id: number
  available_balance_paise: number
  held_balance_paise: number
  merchant_funds_paise: number
  total_credits_paise: number
  total_debits_paise: number
}

export type LedgerEntry = {
  id: number
  amount_paise: number
  entry_type: string
  related_payout_id: number | null
  created_at: string
  metadata: Record<string, unknown>
}

export type Payout = {
  id: number
  bank_account_id: number
  amount_paise: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  attempts: number
  created_at: string
  updated_at: string
}

export function listMerchants() {
  return request<Merchant[]>('/merchants')
}

export function getBalance(merchantId: number) {
  return request<Balance>(`/merchants/${merchantId}/balance`, {
    headers: { 'X-Merchant-Id': String(merchantId) },
  })
}

export function getLedger(merchantId: number) {
  return request<LedgerEntry[]>(`/merchants/${merchantId}/ledger`, {
    headers: { 'X-Merchant-Id': String(merchantId) },
  })
}

export function listPayouts(merchantId: number) {
  return request<Payout[]>('/payouts', {
    headers: { 'X-Merchant-Id': String(merchantId) },
  })
}

export function createPayout(merchantId: number, body: { amount_paise: number; bank_account_id: number }) {
  return request<Payout>('/payouts', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: {
      'X-Merchant-Id': String(merchantId),
      'Idempotency-Key': crypto.randomUUID(),
    },
  })
}

