from django.test import TestCase

from apps.payouts.models import BankAccount, LedgerEntry, Merchant, Payout
from apps.payouts.services.ledger import get_balance_summary
from apps.payouts.services.payout_service import process_payout_once


class RefundTests(TestCase):
    def test_failed_processing_payout_creates_refund(self):
        merchant = Merchant.objects.create(name="Refund Merchant")
        bank_account = BankAccount.objects.create(
            merchant=merchant,
            account_holder_name="Refund Merchant",
            bank_name="ICICI Bank",
            ifsc="ICIC0000001",
            account_number_last4="9876",
        )
        LedgerEntry.objects.create(
            merchant=merchant,
            amount_paise=10000,
            entry_type=LedgerEntry.EntryType.CREDIT_CUSTOMER_PAYMENT,
        )
        payout = Payout.objects.create(
            merchant=merchant,
            bank_account=bank_account,
            amount_paise=6000,
            status=Payout.Status.PENDING,
        )
        LedgerEntry.objects.create(
            merchant=merchant,
            amount_paise=6000,
            entry_type=LedgerEntry.EntryType.DEBIT_PAYOUT_HOLD,
            related_payout=payout,
        )

        process_payout_once(payout.id, "failed")
        payout.refresh_from_db()

        self.assertEqual(payout.status, Payout.Status.FAILED)
        self.assertEqual(
            LedgerEntry.objects.filter(
                related_payout=payout,
                entry_type=LedgerEntry.EntryType.CREDIT_PAYOUT_REFUND,
            ).count(),
            1,
        )
        self.assertEqual(get_balance_summary(merchant.id)["available_balance_paise"], 10000)

