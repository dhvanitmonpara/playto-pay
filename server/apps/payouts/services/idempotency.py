import hashlib
import json
from datetime import timedelta

from django.utils import timezone


def hash_request_body(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expires_at():
    return timezone.now() + timedelta(hours=24)

