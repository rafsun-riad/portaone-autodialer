from __future__ import annotations

import os
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from dotenv import dotenv_values


def normalize_bangladesh_number(value: str) -> str:
    stripped = (value or "").strip()
    if not stripped:
        return ""

    digits = "".join(character for character in stripped if character.isdigit())
    if not digits or any(character.isalpha() for character in stripped):
        return stripped
    if digits.startswith("88"):
        return digits
    return f"88{digits}"


def parse_external_datetime(value: str | None):
    if not value:
        return None

    parsed = parse_datetime(value.replace(" ", "T"))
    if parsed is None:
        parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


def build_public_url(path: str) -> str:
    env_values = dotenv_values(settings.BASE_DIR / ".env")
    public_origin = (
        env_values.get("WEBHOOK_ORIGIN")
        or env_values.get("BACKEND_API_ORIGIN")
        or os.getenv("WEBHOOK_ORIGIN")
        or os.getenv("BACKEND_API_ORIGIN")
        or settings.WEBHOOK_ORIGIN
    )
    return urljoin(f"{str(public_origin).rstrip('/')}/", path.lstrip("/"))
