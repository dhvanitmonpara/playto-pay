from django.contrib import admin

from apps.payouts.models import BankAccount, IdempotencyKey, LedgerEntry, Merchant, Payout


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "created_at"]


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ["id", "merchant", "bank_name", "account_number_last4", "is_active"]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ["id", "merchant", "entry_type", "amount_paise", "related_payout", "created_at"]
    list_filter = ["entry_type"]


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ["id", "merchant", "amount_paise", "status", "attempts", "created_at", "updated_at"]
    list_filter = ["status"]


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ["id", "merchant", "key", "status_code", "in_progress", "expires_at"]

