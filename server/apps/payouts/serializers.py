from rest_framework import serializers

from apps.payouts.models import BankAccount, LedgerEntry, Merchant, Payout
from apps.payouts.services.ledger import get_balance_summary


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            "id",
            "account_holder_name",
            "bank_name",
            "ifsc",
            "account_number_last4",
            "is_active",
        ]


class MerchantSerializer(serializers.ModelSerializer):
    bank_accounts = BankAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Merchant
        fields = ["id", "name", "bank_accounts", "created_at"]


class BalanceSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField()
    available_balance_paise = serializers.IntegerField()
    held_balance_paise = serializers.IntegerField()
    merchant_funds_paise = serializers.IntegerField()
    total_credits_paise = serializers.IntegerField()
    total_debits_paise = serializers.IntegerField()

    @classmethod
    def for_merchant(cls, merchant_id: int):
        return cls({"merchant_id": merchant_id, **get_balance_summary(merchant_id)})


class LedgerEntrySerializer(serializers.ModelSerializer):
    related_payout_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "amount_paise",
            "entry_type",
            "related_payout_id",
            "metadata",
            "created_at",
        ]


class PayoutSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "merchant_id",
            "bank_account_id",
            "bank_account",
            "amount_paise",
            "status",
            "attempts",
            "created_at",
            "updated_at",
        ]

