from django.db import transaction
from django.utils import timezone
from rest_framework import status

from apps.payouts.models import BankAccount, IdempotencyKey, LedgerEntry, Merchant, Payout
from apps.payouts.services.idempotency import expires_at, hash_request_body
from apps.payouts.services.ledger import get_balance_summary
from apps.payouts.services.state_machine import transition_payout


def serialize_payout(payout: Payout) -> dict:
    return {
        "id": payout.id,
        "merchant_id": payout.merchant_id,
        "bank_account_id": payout.bank_account_id,
        "amount_paise": payout.amount_paise,
        "status": payout.status,
        "attempts": payout.attempts,
        "created_at": payout.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": payout.updated_at.isoformat().replace("+00:00", "Z"),
    }


def create_payout_request(*, merchant_id: int, idempotency_key: str, request_body: dict) -> tuple[int, dict]:
    request_hash = hash_request_body(request_body)

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

        if not created and idem.is_expired:
            idem.request_hash = request_hash
            idem.response_body = None
            idem.status_code = None
            idem.in_progress = True
            idem.expires_at = expires_at()
            idem.save(
                update_fields=[
                    "request_hash",
                    "response_body",
                    "status_code",
                    "in_progress",
                    "expires_at",
                ]
            )
        elif not created:
            if idem.request_hash != request_hash:
                return status.HTTP_409_CONFLICT, {
                    "detail": "Idempotency-Key was already used with a different request body."
                }
            if idem.response_body is not None and idem.status_code is not None:
                return idem.status_code, idem.response_body
            return status.HTTP_409_CONFLICT, {"detail": "Request with this Idempotency-Key is still in progress."}

        response_status, response_body = _create_payout_after_lock(merchant, request_body)
        idem.response_body = response_body
        idem.status_code = response_status
        idem.in_progress = False
        idem.save(update_fields=["response_body", "status_code", "in_progress"])
        return response_status, response_body


def _create_payout_after_lock(merchant: Merchant, request_body: dict) -> tuple[int, dict]:
    amount_paise = request_body.get("amount_paise")
    bank_account_id = request_body.get("bank_account_id")

    if type(amount_paise) is not int or amount_paise <= 0:
        return status.HTTP_400_BAD_REQUEST, {"amount_paise": ["Must be a positive integer."]}

    bank_account = BankAccount.objects.filter(
        id=bank_account_id,
        merchant=merchant,
        is_active=True,
    ).first()
    if bank_account is None:
        return status.HTTP_400_BAD_REQUEST, {"bank_account_id": ["Invalid bank account for merchant."]}

    balance = get_balance_summary(merchant.id)
    if balance["available_balance_paise"] < amount_paise:
        return status.HTTP_400_BAD_REQUEST, {
            "detail": "Insufficient funds.",
            "available_balance_paise": balance["available_balance_paise"],
        }

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
        metadata={"reason": "payout_request"},
    )
    return status.HTTP_201_CREATED, serialize_payout(payout)


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
        if payout.status == Payout.Status.PENDING:
            transition_payout(payout, Payout.Status.PROCESSING)
            payout.refresh_from_db()
        if payout.status != Payout.Status.PROCESSING:
            return payout

        payout.attempts += 1
        payout.save(update_fields=["attempts", "updated_at"])

        if result == "completed":
            return transition_payout(payout, Payout.Status.COMPLETED)
        if result == "failed":
            return fail_payout_with_refund(payout, reason="bank_failed")
        if result == "stuck":
            return payout
        raise ValueError(f"Unknown payout processor result: {result}")


def fail_stale_processing_payout(payout_id: int) -> Payout:
    with transaction.atomic():
        payout = Payout.objects.select_for_update().select_related("merchant").get(id=payout_id)
        if payout.status == Payout.Status.PROCESSING:
            return fail_payout_with_refund(payout, reason="max_attempts_exceeded")
        return payout


def stale_processing_queryset():
    return Payout.objects.filter(
        status=Payout.Status.PROCESSING,
        updated_at__lt=timezone.now() - timezone.timedelta(seconds=30),
    )
