import threading

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.payouts.models import BankAccount, LedgerEntry, Merchant, Payout
from apps.payouts.services.ledger import get_balance_summary


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PAYOUTS_AUTO_ENQUEUE=False)
class PayoutConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.merchant = Merchant.objects.create(name="Concurrent Merchant")
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_holder_name="Concurrent Merchant",
            bank_name="Axis Bank",
            ifsc="UTIB0000001",
            account_number_last4="4321",
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            entry_type=LedgerEntry.EntryType.CREDIT_CUSTOMER_PAYMENT,
        )

    def test_two_concurrent_payouts_cannot_overdraw(self):
        self.assertTrue(connection.features.has_select_for_update)
        barrier = threading.Barrier(2)
        results = []

        def submit(index):
            close_old_connections()
            client = APIClient()
            barrier.wait()
            response = client.post(
                "/api/v1/payouts/",
                {"amount_paise": 6000, "bank_account_id": self.bank_account.id},
                format="json",
                HTTP_X_MERCHANT_ID=str(self.merchant.id),
                HTTP_IDEMPOTENCY_KEY=f"33333333-3333-4333-8333-33333333333{index}",
            )
            results.append((response.status_code, response.json()))
            close_old_connections()

        threads = [threading.Thread(target=submit, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        status_codes = sorted(status_code for status_code, _ in results)
        self.assertEqual(status_codes, [201, 400])
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(
            LedgerEntry.objects.filter(entry_type=LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD).count(),
            1,
        )
        self.assertEqual(get_balance_summary(self.merchant.id)["available_balance_paise"], 4000)
