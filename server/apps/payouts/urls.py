from django.urls import path

from apps.payouts.views import (
    MerchantBalanceView,
    MerchantLedgerView,
    MerchantListView,
    PayoutListCreateView,
)

urlpatterns = [
    path("merchants", MerchantListView.as_view(), name="merchant-list-no-slash"),
    path("merchants/", MerchantListView.as_view(), name="merchant-list"),
    path("merchants/<int:merchant_id>/balance", MerchantBalanceView.as_view(), name="merchant-balance-no-slash"),
    path("merchants/<int:merchant_id>/balance/", MerchantBalanceView.as_view(), name="merchant-balance"),
    path("merchants/<int:merchant_id>/ledger", MerchantLedgerView.as_view(), name="merchant-ledger-no-slash"),
    path("merchants/<int:merchant_id>/ledger/", MerchantLedgerView.as_view(), name="merchant-ledger"),
    path("payouts", PayoutListCreateView.as_view(), name="payout-list-create-no-slash"),
    path("payouts/", PayoutListCreateView.as_view(), name="payout-list-create"),
]
