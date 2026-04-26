from django.db.models import BigIntegerField, Case, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from apps.payouts.models import LedgerEntry, Payout


CREDIT_TYPES = [
    LedgerEntry.EntryType.CREDIT_CUSTOMER_PAYMENT,
    LedgerEntry.EntryType.CREDIT_PAYOUT_REFUND,
]
DEBIT_TYPES = [LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD]
ACTIVE_PAYOUT_STATUSES = [Payout.Status.PENDING, Payout.Status.PROCESSING]


def get_balance_summary(merchant_id: int) -> dict:
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
        related_payout__status__in=ACTIVE_PAYOUT_STATUSES,
    ).aggregate(held_balance_paise=Coalesce(Sum("amount_paise"), Value(0)))
    totals["held_balance_paise"] = held["held_balance_paise"]
    totals["merchant_funds_paise"] = totals["available_balance_paise"] + totals["held_balance_paise"]
    return totals


def create_customer_credit(merchant_id: int, amount_paise: int, metadata: dict | None = None) -> LedgerEntry:
    return LedgerEntry.objects.create(
        merchant_id=merchant_id,
        amount_paise=amount_paise,
        entry_type=LedgerEntry.EntryType.CREDIT_CUSTOMER_PAYMENT,
        metadata=metadata or {},
    )
