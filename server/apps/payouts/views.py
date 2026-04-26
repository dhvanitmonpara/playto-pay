from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payouts.models import LedgerEntry, Merchant, Payout
from apps.payouts.serializers import (
    BalanceSerializer,
    LedgerEntrySerializer,
    MerchantSerializer,
    PayoutSerializer,
)
from apps.payouts.services.payout_service import create_payout_request


def _merchant_from_header(request):
    merchant_id = request.headers.get("X-Merchant-Id")
    if not merchant_id:
        return None
    try:
        return int(merchant_id)
    except ValueError:
        return None


def _validate_selected_merchant(request, path_merchant_id: int) -> Response | None:
    header_merchant_id = _merchant_from_header(request)
    if header_merchant_id is None:
        return None
    if header_merchant_id != path_merchant_id:
        return Response(
            {"detail": "X-Merchant-Id does not match the selected merchant."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.prefetch_related("bank_accounts").order_by("id")
        return Response(MerchantSerializer(merchants, many=True).data)


class MerchantBalanceView(APIView):
    def get(self, request, merchant_id: int):
        mismatch = _validate_selected_merchant(request, merchant_id)
        if mismatch:
            return mismatch
        get_object_or_404(Merchant, id=merchant_id)
        return Response(BalanceSerializer.for_merchant(merchant_id).data)


class MerchantLedgerView(APIView):
    def get(self, request, merchant_id: int):
        mismatch = _validate_selected_merchant(request, merchant_id)
        if mismatch:
            return mismatch
        get_object_or_404(Merchant, id=merchant_id)
        entries = LedgerEntry.objects.filter(merchant_id=merchant_id).order_by("-created_at", "-id")[:50]
        return Response(LedgerEntrySerializer(entries, many=True).data)


class PayoutListCreateView(APIView):
    def get(self, request):
        merchant_id = _merchant_from_header(request)
        if merchant_id is None:
            return Response({"detail": "X-Merchant-Id header is required."}, status=status.HTTP_400_BAD_REQUEST)
        payouts = (
            Payout.objects.filter(merchant_id=merchant_id)
            .select_related("bank_account")
            .order_by("-created_at", "-id")[:50]
        )
        return Response(PayoutSerializer(payouts, many=True).data)

    def post(self, request):
        merchant_id = _merchant_from_header(request)
        if merchant_id is None:
            return Response({"detail": "X-Merchant-Id header is required."}, status=status.HTTP_400_BAD_REQUEST)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response({"detail": "Idempotency-Key header is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not Merchant.objects.filter(id=merchant_id).exists():
            return Response({"detail": "Merchant not found."}, status=status.HTTP_404_NOT_FOUND)

        response_status, response_body = create_payout_request(
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            request_body=dict(request.data),
        )
        if response_status == status.HTTP_201_CREATED and settings.PAYOUTS_AUTO_ENQUEUE:
            try:
                from apps.payouts.tasks import process_pending_payouts

                process_pending_payouts.delay()
            except Exception:
                # Payout remains pending; the worker/beat will pick it up when available.
                pass
        return Response(response_body, status=response_status)
