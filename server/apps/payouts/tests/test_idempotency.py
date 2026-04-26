from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.payouts.models import BankAccount, LedgerEntry, Merchant, Payout


@override_settings(PAYOUTS_AUTO_ENQUEUE=False)
class IdempotencyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.merchant = Merchant.objects.create(name="Test Merchant")
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_holder_name="Test Merchant",
            bank_name="HDFC Bank",
            ifsc="HDFC0000001",
            account_number_last4="1234",
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            entry_type=LedgerEntry.EntryType.CREDIT_CUSTOMER_PAYMENT,
        )

    def test_same_key_and_body_returns_same_response_without_duplicate_payout(self):
        body = {"amount_paise": 6000, "bank_account_id": self.bank_account.id}
        headers = {
            "HTTP_X_MERCHANT_ID": str(self.merchant.id),
            "HTTP_IDEMPOTENCY_KEY": "11111111-1111-4111-8111-111111111111",
        }

        first = self.client.post("/api/v1/payouts/", body, format="json", **headers)
        second = self.client.post("/api/v1/payouts/", body, format="json", **headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(
            LedgerEntry.objects.filter(entry_type=LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD).count(),
            1,
        )

    def test_same_key_different_body_returns_conflict(self):
        headers = {
            "HTTP_X_MERCHANT_ID": str(self.merchant.id),
            "HTTP_IDEMPOTENCY_KEY": "22222222-2222-4222-8222-222222222222",
        }

        first = self.client.post(
            "/api/v1/payouts/",
            {"amount_paise": 6000, "bank_account_id": self.bank_account.id},
            format="json",
            **headers,
        )
        second = self.client.post(
            "/api/v1/payouts/",
            {"amount_paise": 5000, "bank_account_id": self.bank_account.id},
            format="json",
            **headers,
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Payout.objects.count(), 1)
