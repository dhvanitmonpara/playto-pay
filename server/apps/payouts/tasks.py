import random

from celery import shared_task
from django.db import transaction

from apps.payouts.models import Payout
from apps.payouts.services.payout_service import (
    fail_stale_processing_payout,
    process_payout_once,
    stale_processing_queryset,
)
from apps.payouts.services.state_machine import transition_payout


def _simulated_bank_result() -> str:
    value = random.random()
    if value < 0.70:
        return "completed"
    if value < 0.90:
        return "failed"
    return "stuck"


@shared_task
def process_pending_payouts(limit: int = 10):
    picked = []
    with transaction.atomic():
        payouts = (
            Payout.objects.select_for_update(skip_locked=True)
            .filter(status=Payout.Status.PENDING)
            .order_by("created_at")[:limit]
        )
        for payout in payouts:
            transition_payout(payout, Payout.Status.PROCESSING)
            picked.append(payout.id)

    for payout_id in picked:
        process_payout.delay(payout_id)
    return picked


@shared_task(bind=True, max_retries=3)
def process_payout(self, payout_id: int):
    try:
        return process_payout_once(payout_id, _simulated_bank_result()).status
    except Exception as exc:
        countdown = 2**self.request.retries
        raise self.retry(exc=exc, countdown=countdown)


@shared_task
def retry_stale_processing_payouts(limit: int = 10):
    payouts = stale_processing_queryset().order_by("updated_at")[:limit]
    scheduled = []
    failed = []
    for payout in payouts:
        if payout.attempts >= 3:
            fail_stale_processing_payout(payout.id)
            failed.append(payout.id)
        else:
            countdown = 2**payout.attempts
            process_payout.apply_async(args=[payout.id], countdown=countdown)
            scheduled.append(payout.id)
    return {"scheduled": scheduled, "failed": failed}

