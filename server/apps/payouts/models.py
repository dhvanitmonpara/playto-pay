from django.db import models
from django.utils import timezone


class Merchant(models.Model):
    name = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BankAccount(models.Model):
    merchant = models.ForeignKey(Merchant, related_name="bank_accounts", on_delete=models.CASCADE)
    account_holder_name = models.CharField(max_length=160)
    bank_name = models.CharField(max_length=160)
    ifsc = models.CharField(max_length=16)
    account_number_last4 = models.CharField(max_length=4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bank_name} ****{self.account_number_last4}"


class Payout(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    merchant = models.ForeignKey(Merchant, related_name="payouts", on_delete=models.PROTECT)
    bank_account = models.ForeignKey(BankAccount, related_name="payouts", on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["merchant", "status"]),
            models.Index(fields=["status", "updated_at"]),
        ]

    def __str__(self):
        return f"Payout {self.id} {self.status} {self.amount_paise}"


class LedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        CREDIT_CUSTOMER_PAYMENT = "CREDIT_CUSTOMER_PAYMENT", "Credit customer payment"
        DEBIT_PAYOUT_HOLD = "DEBIT_PAYOUT_HOLD", "Debit payout hold"
        CREDIT_PAYOUT_REFUND = "CREDIT_PAYOUT_REFUND", "Credit payout refund"

    CREDIT_TYPES = {EntryType.CREDIT_CUSTOMER_PAYMENT, EntryType.CREDIT_PAYOUT_REFUND}
    DEBIT_TYPES = {EntryType.DEBIT_PAYOUT_HOLD}

    merchant = models.ForeignKey(Merchant, related_name="ledger_entries", on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    entry_type = models.CharField(max_length=40, choices=EntryType.choices)
    related_payout = models.ForeignKey(
        Payout,
        related_name="ledger_entries",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["merchant", "created_at"]),
            models.Index(fields=["merchant", "entry_type"]),
            models.Index(fields=["related_payout", "entry_type"]),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount_paise}"


class IdempotencyKey(models.Model):
    merchant = models.ForeignKey(Merchant, related_name="idempotency_keys", on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    response_body = models.JSONField(null=True, blank=True)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    in_progress = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["merchant", "key"], name="uniq_idempotency_key_per_merchant"),
        ]
        indexes = [
            models.Index(fields=["merchant", "key"]),
            models.Index(fields=["expires_at"]),
        ]

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    def __str__(self):
        return f"{self.merchant_id}:{self.key}"

