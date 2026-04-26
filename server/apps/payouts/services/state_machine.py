from apps.payouts.models import Payout


class IllegalPayoutTransition(ValueError):
    pass


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

