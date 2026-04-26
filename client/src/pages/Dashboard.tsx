import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  createPayout,
  getBalance,
  getLedger,
  listMerchants,
  listPayouts,
} from '../api/client'
import type { Balance, LedgerEntry, Merchant, Payout } from '../api/client'

function inr(paise: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(paise / 100)
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

const statusClass: Record<Payout['status'], string> = {
  pending: 'bg-amber-100 text-amber-800',
  processing: 'bg-blue-100 text-blue-800',
  completed: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-rose-100 text-rose-800',
}

export function Dashboard() {
  const [merchants, setMerchants] = useState<Merchant[]>([])
  const [merchantId, setMerchantId] = useState<number | null>(null)
  const [balance, setBalance] = useState<Balance | null>(null)
  const [ledger, setLedger] = useState<LedgerEntry[]>([])
  const [payouts, setPayouts] = useState<Payout[]>([])
  const [amountRupees, setAmountRupees] = useState('')
  const [bankAccountId, setBankAccountId] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  const merchant = merchants.find((item) => item.id === merchantId) ?? null

  useEffect(() => {
    listMerchants().then((items) => {
      setMerchants(items)
      if (items[0]) {
        setMerchantId(items[0].id)
        setBankAccountId(items[0].bank_accounts[0]?.id ?? null)
      }
    }).catch((error) => setMessage(error.message))
  }, [])

  useEffect(() => {
    if (!merchantId) return
    const selectedMerchantId = merchantId

    let active = true
    async function load() {
      try {
        const [nextBalance, nextLedger, nextPayouts] = await Promise.all([
          getBalance(selectedMerchantId),
          getLedger(selectedMerchantId),
          listPayouts(selectedMerchantId),
        ])
        if (active) {
          setBalance(nextBalance)
          setLedger(nextLedger)
          setPayouts(nextPayouts)
        }
      } catch (error) {
        if (error instanceof Error) setMessage(error.message)
      }
    }

    load()
    const timer = window.setInterval(load, 3000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [merchantId])

  useEffect(() => {
    setBankAccountId(merchant?.bank_accounts[0]?.id ?? null)
  }, [merchant])

  async function submitPayout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!merchantId || !bankAccountId) return

    const amount_paise = Math.round(Number(amountRupees) * 100)
    setLoading(true)
    setMessage('')
    try {
      await createPayout(merchantId, { amount_paise, bank_account_id: bankAccountId })
      setAmountRupees('')
      const [nextBalance, nextLedger, nextPayouts] = await Promise.all([
        getBalance(merchantId),
        getLedger(merchantId),
        listPayouts(merchantId),
      ])
      setBalance(nextBalance)
      setLedger(nextLedger)
      setPayouts(nextPayouts)
      setMessage('Payout request created.')
    } catch (error) {
      if (error instanceof Error) setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-[#f4f0e8] text-slate-950">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-8">
        <header className="rounded-[2rem] border border-slate-900 bg-[#d8ff72] p-6 shadow-[8px_8px_0_#0f172a]">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm font-black uppercase tracking-[0.2em]">Playto Pay</p>
              <h1 className="mt-2 text-4xl font-black tracking-tight md:text-6xl">Merchant payout engine</h1>
              <p className="mt-2 max-w-2xl text-sm font-medium text-slate-700">
                Demo dashboard backed by ledger-derived balances, idempotent payout creation, and a Celery processor.
              </p>
            </div>
            <label className="flex flex-col gap-2 text-sm font-bold">
              Merchant
              <select
                className="rounded-2xl border-2 border-slate-900 bg-white px-4 py-3 font-semibold"
                value={merchantId ?? ''}
                onChange={(event) => setMerchantId(Number(event.target.value))}
              >
                {merchants.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>

        {message && (
          <div className="rounded-2xl border-2 border-slate-900 bg-white px-4 py-3 font-semibold shadow-[4px_4px_0_#0f172a]">
            {message}
          </div>
        )}

        <section className="grid gap-4 md:grid-cols-4">
          <BalanceCard label="Available" value={balance ? inr(balance.available_balance_paise) : '-'} />
          <BalanceCard label="Held" value={balance ? inr(balance.held_balance_paise) : '-'} />
          <BalanceCard label="Credits" value={balance ? inr(balance.total_credits_paise) : '-'} />
          <BalanceCard label="Debits" value={balance ? inr(balance.total_debits_paise) : '-'} />
        </section>

        <section className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
          <form onSubmit={submitPayout} className="rounded-[2rem] border-2 border-slate-900 bg-white p-5 shadow-[6px_6px_0_#0f172a]">
            <h2 className="text-2xl font-black">Request payout</h2>
            <p className="mt-1 text-sm text-slate-600">A fresh idempotency key is generated for every submit.</p>
            <label className="mt-5 flex flex-col gap-2 text-sm font-bold">
              Amount in INR
              <input
                className="rounded-2xl border-2 border-slate-900 px-4 py-3"
                min="0"
                step="0.01"
                value={amountRupees}
                onChange={(event) => setAmountRupees(event.target.value)}
                placeholder="100.00"
                required
              />
            </label>
            <label className="mt-4 flex flex-col gap-2 text-sm font-bold">
              Bank account
              <select
                className="rounded-2xl border-2 border-slate-900 px-4 py-3"
                value={bankAccountId ?? ''}
                onChange={(event) => setBankAccountId(Number(event.target.value))}
                required
              >
                {merchant?.bank_accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.bank_name} ****{account.account_number_last4}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="mt-5 w-full rounded-2xl border-2 border-slate-900 bg-slate-950 px-4 py-3 font-black text-white disabled:opacity-60"
              disabled={loading}
              type="submit"
            >
              {loading ? 'Creating...' : 'Create payout hold'}
            </button>
          </form>

          <Panel title="Payout history">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-sm">
                <thead>
                  <tr className="border-b-2 border-slate-900">
                    <th className="py-2">ID</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Attempts</th>
                    <th>Created</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {payouts.map((payout) => (
                    <tr key={payout.id} className="border-b border-slate-200">
                      <td className="py-3 font-bold">#{payout.id}</td>
                      <td>{inr(payout.amount_paise)}</td>
                      <td>
                        <span className={`rounded-full px-2 py-1 text-xs font-black ${statusClass[payout.status]}`}>
                          {payout.status}
                        </span>
                      </td>
                      <td>{payout.attempts}</td>
                      <td>{formatTime(payout.created_at)}</td>
                      <td>{formatTime(payout.updated_at)}</td>
                    </tr>
                  ))}
                  {payouts.length === 0 && (
                    <tr>
                      <td className="py-8 text-center text-slate-500" colSpan={6}>No payouts yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </section>

        <Panel title="Recent ledger entries">
          <div className="grid gap-3">
            {ledger.map((entry) => (
              <div key={entry.id} className="grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-[1fr_auto_auto] md:items-center">
                <div>
                  <p className="font-black">{entry.entry_type}</p>
                  <p className="text-xs text-slate-500">{formatTime(entry.created_at)}</p>
                </div>
                <p className="font-mono text-sm">Payout: {entry.related_payout_id ?? '-'}</p>
                <p className="text-lg font-black">{inr(entry.amount_paise)}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </main>
  )
}

function BalanceCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.5rem] border-2 border-slate-900 bg-white p-5 shadow-[5px_5px_0_#0f172a]">
      <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-black">{value}</p>
    </div>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-[2rem] border-2 border-slate-900 bg-white p-5 shadow-[6px_6px_0_#0f172a]">
      <h2 className="mb-4 text-2xl font-black">{title}</h2>
      {children}
    </section>
  )
}
