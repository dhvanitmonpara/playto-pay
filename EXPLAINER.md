# The Ledger

Balance calculation code from `server/apps/payouts/services/ledger.py`:

```python
totals = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
    total_credits_paise=Coalesce(
        Sum("amount_paise", filter=Q(entry_type__in=CREDIT_TYPES)),
        Value(0),
    ),
    total_debits_paise=Coalesce(
        Sum("amount_paise", filter=Q(entry_type__in=DEBIT_TYPES)),
        Value(0),
    ),
    available_balance_paise=Coalesce(
        Sum(
            Case(
                When(entry_type__in=CREDIT_TYPES, then="amount_paise"),
                When(entry_type__in=DEBIT_TYPES, then=-1 * F("amount_paise")),
                default=Value(0),
                output_field=BigIntegerField(),
            )
        ),
        Value(0),
    ),
)
held = LedgerEntry.objects.filter(
    merchant_id=merchant_id,
    entry_type=LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD,
    related_payout__status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING],
).aggregate(held_balance_paise=Coalesce(Sum("amount_paise"), Value(0)))
```

Credits and debits are modeled as immutable ledger rows because money movement should be auditable. A payout request does not subtract a mutable merchant balance column. It writes a `DEBIT_PAYOUT_HOLD` entry, and balance is derived from the ledger.

Ledger entries are never updated or deleted. Failed payouts are handled with compensating refund entries instead of rewriting history, which preserves auditability and avoids hiding money movement.

All money is stored as integer paise in `BigIntegerField`. No `FloatField` is used, so there is no floating point rounding drift. `DecimalField` is unnecessary because the domain only needs the smallest currency unit.

Invariant:

```text
available_balance_paise = sum(CREDIT_CUSTOMER_PAYMENT + CREDIT_PAYOUT_REFUND) - sum(DEBIT_PAYOUT_HOLD)
held_balance_paise = sum(DEBIT_PAYOUT_HOLD for pending/processing payouts)
merchant_funds_paise = available_balance_paise + held_balance_paise
```

Completed payouts remain debits. Failed payouts create a refund credit for the same payout, restoring available balance without deleting the original hold.

We never delete or mutate ledger entries. Failed payouts are neutralized via compensating entries (refunds), preserving full auditability.

`available_balance` excludes payout holds, while `held_balance` represents funds reserved but not yet settled. The sum of both reflects total merchant funds.

# The Lock

Exact payout request lock from `server/apps/payouts/services/payout_service.py`:

```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    idem, created = IdempotencyKey.objects.select_for_update().get_or_create(
        merchant=merchant,
        key=idempotency_key,
        defaults={
            "request_hash": request_hash,
            "expires_at": expires_at(),
            "in_progress": True,
        },
    )
    response_status, response_body = _create_payout_after_lock(merchant, request_body)
```

The balance check inside the same transaction:

```python
balance = get_balance_summary(merchant.id)
if balance["available_balance_paise"] < amount_paise:
    return status.HTTP_400_BAD_REQUEST, {
        "detail": "Insufficient funds.",
        "available_balance_paise": balance["available_balance_paise"],
    }

payout = Payout.objects.create(...)
LedgerEntry.objects.create(
    merchant=merchant,
    amount_paise=amount_paise,
    entry_type=LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD,
    related_payout=payout,
    metadata={"reason": "payout_request"},
)
```

`select_for_update()` takes a PostgreSQL row lock on the merchant. We use the merchant row as a coarse-grained mutex to serialize payout creation. While ledger rows are not individually locked, all balance-affecting writes happen within the same transaction, so subsequent transactions observe the committed ledger state before recalculating balance.

This behavior relies on PostgreSQL's default `READ COMMITTED` isolation level, where each query observes the latest committed state at execution time.
This ensures that each balance read reflects the latest committed ledger state after previous transactions complete.

Python-level balance checks without database locks are unsafe because they operate on stale reads. Two workers can both read `10000`, both decide a `6000` payout is allowed, and both insert holds. That cannot prevent concurrent writes from violating the ledger invariant.

Optimistic concurrency control was not used because strict serialization guarantees are required for money movement, which are more reliably enforced with database row-level locks.

# The Idempotency

`IdempotencyKey` is scoped by merchant and key:

```python
models.UniqueConstraint(fields=["merchant", "key"], name="uniq_idempotency_key_per_merchant")
```

The request hash is a SHA-256 hash of canonical JSON:

```python
def hash_request_body(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Same merchant, same key, same body:

```python
if idem.request_hash == request_hash and idem.response_body is not None:
    return idem.status_code, idem.response_body
```

The exact stored response body and status code are returned. No second payout or ledger hold is created.

Same merchant, same key, different body:

```python
if idem.request_hash != request_hash:
    return status.HTTP_409_CONFLICT, {
        "detail": "Idempotency-Key was already used with a different request body."
    }
```

If the first request is still in flight, the second request blocks on the same merchant row lock. The `in_progress` marker protects crash/partial-write cases: for example, a request can reserve the key and then fail before storing the final response. That avoids ambiguous duplicate processing.

Concurrent creation of the same idempotency key is protected by a unique constraint at the database level. One transaction succeeds, and the other observes the existing row after retry, preventing duplicate payout creation.

Keys expire after 24 hours through `expires_at`. An expired key can be reused by overwriting the old idempotency row inside the same merchant lock.
Key reuse after expiry is allowed only because expiry guarantees the original request lifecycle has completed and its response is no longer required for replay.

## Worker Concurrency

Payout processing is protected with row-level locking. Each worker acquires a lock on the payout row before processing, so multiple workers cannot process the same payout concurrently. This prevents duplicate state transitions or double refunds.
Payout selection for processing is done inside a transaction using row-level locking (e.g., `select_for_update` with `skip_locked`), ensuring that multiple workers do not pick the same payout concurrently.

## Retry Logic

Payouts that remain in processing beyond a threshold are retried with exponential backoff up to a fixed number of attempts. After exceeding the retry limit, the payout is marked as failed and a compensating refund entry is created atomically.
Retry attempts are tracked on the payout record, ensuring retries are bounded, idempotent, and do not trigger duplicate completion or refund logic.

# The State Machine

Transition validation code from `server/apps/payouts/services/state_machine.py`:

```python
ALLOWED_TRANSITIONS = {
    Payout.Status.PENDING: {Payout.Status.PROCESSING},
    Payout.Status.PROCESSING: {Payout.Status.COMPLETED, Payout.Status.FAILED},
    Payout.Status.COMPLETED: set(),
    Payout.Status.FAILED: set(),
}

def transition_payout(payout: Payout, new_status: str) -> Payout:
    if new_status not in ALLOWED_TRANSITIONS.get(payout.status, set()):
        raise IllegalPayoutTransition(f"Illegal payout transition: {payout.status} -> {new_status}")

    payout.status = new_status
    payout.save(update_fields=["status", "updated_at"])
    return payout
```

`failed -> completed` is blocked because `Payout.Status.FAILED` maps to an empty set. `completed -> pending` is also blocked.

Failed transition and refund happen in one transaction:

```python
def fail_payout_with_refund(payout: Payout, reason: str) -> Payout:
    transition_payout(payout, Payout.Status.FAILED)
    LedgerEntry.objects.create(
        merchant=payout.merchant,
        amount_paise=payout.amount_paise,
        entry_type=LedgerEntry.EntryType.CREDIT_PAYOUT_REFUND,
        related_payout=payout,
        metadata={"reason": reason},
    )
    return payout

def process_payout_once(payout_id: int, result: str) -> Payout:
    with transaction.atomic():
        payout = Payout.objects.select_for_update().select_related("merchant").get(id=payout_id)
        ...
        if result == "failed":
            return fail_payout_with_refund(payout, reason="bank_failed")
```

If the transaction fails or rolls back, neither payout state nor ledger entries are persisted, preventing partial money movement. If a worker crashes mid-processing, the transaction is rolled back and the payout remains in its previous state, allowing it to be safely retried without partial effects.

# The AI Audit

A realistic unsafe first draft:

```python
def create_payout_bad(merchant, amount_paise, bank_account):
    balance = get_balance_summary(merchant.id)["available_balance_paise"]
    if balance < amount_paise:
        raise InsufficientFunds()

    payout = Payout.objects.create(
        merchant=merchant,
        bank_account=bank_account,
        amount_paise=amount_paise,
        status=Payout.Status.PENDING,
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        amount_paise=amount_paise,
        entry_type=LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD,
        related_payout=payout,
    )
    return payout
```

Why it is wrong:

- The balance read is not protected by a row lock.
- Two concurrent requests can both see the same available balance.
- Both can pass the insufficient-funds check.
- Both can insert payout holds, creating an overdraft.
- Idempotency is not checked in the same critical section.

Corrected version:

```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    idem, created = IdempotencyKey.objects.select_for_update().get_or_create(
        merchant=merchant,
        key=idempotency_key,
        defaults={
            "request_hash": request_hash,
            "expires_at": expires_at(),
            "in_progress": True,
        },
    )

    balance = get_balance_summary(merchant.id)
    if balance["available_balance_paise"] < amount_paise:
        return 400, {"detail": "Insufficient funds."}

    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(
        merchant=merchant,
        amount_paise=amount_paise,
        entry_type=LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD,
        related_payout=payout,
    )
```

The corrected code serializes all payout creation for a merchant, calculates balance from the database inside the transaction, writes the hold ledger row before commit, and stores the idempotent response in the same transaction.
