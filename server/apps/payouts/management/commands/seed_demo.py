from django.core.management.base import BaseCommand
from django.db import transaction

from apps.payouts.models import BankAccount, LedgerEntry, Merchant


DEMO_MERCHANTS = [
    {
        "id": 1,
        "name": "Jaipur Textiles",
        "bank": {
            "account_holder_name": "Jaipur Textiles Pvt Ltd",
            "bank_name": "HDFC Bank",
            "ifsc": "HDFC0001234",
            "account_number_last4": "4421",
        },
        "credits": [250000, 125000, 64000],
    },
    {
        "id": 2,
        "name": "Kochi Spices",
        "bank": {
            "account_holder_name": "Kochi Spices LLP",
            "bank_name": "ICICI Bank",
            "ifsc": "ICIC0005678",
            "account_number_last4": "8810",
        },
        "credits": [500000, 75000, 42000],
    },
    {
        "id": 3,
        "name": "Pune SaaS Labs",
        "bank": {
            "account_holder_name": "Pune SaaS Labs",
            "bank_name": "Axis Bank",
            "ifsc": "UTIB0009012",
            "account_number_last4": "1029",
        },
        "credits": [900000, 130000, 210000],
    },
]


class Command(BaseCommand):
    help = "Seed demo merchants, bank accounts, and customer-payment ledger credits."

    @transaction.atomic
    def handle(self, *args, **options):
        for merchant_data in DEMO_MERCHANTS:
            merchant, _ = Merchant.objects.update_or_create(
                id=merchant_data["id"],
                defaults={"name": merchant_data["name"]},
            )
            BankAccount.objects.update_or_create(
                merchant=merchant,
                defaults=merchant_data["bank"],
            )
            if not LedgerEntry.objects.filter(
                merchant=merchant,
                entry_type=LedgerEntry.EntryType.CREDIT_CUSTOMER_PAYMENT,
                metadata__seed="demo",
            ).exists():
                for index, amount_paise in enumerate(merchant_data["credits"], start=1):
                    LedgerEntry.objects.create(
                        merchant=merchant,
                        amount_paise=amount_paise,
                        entry_type=LedgerEntry.EntryType.CREDIT_CUSTOMER_PAYMENT,
                        metadata={"seed": "demo", "payment_number": index},
                    )

        self.stdout.write(self.style.SUCCESS("Seeded demo merchants: 1, 2, 3"))

