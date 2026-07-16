from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

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


def add_url_query_params(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def build_versioned_media_url(path: str, version: str | None) -> str:
    public_url = build_public_url(path)
    if not version:
        return public_url
    return add_url_query_params(public_url, {"v": version})


def build_public_playback_audio_url(
    campaign_id: int, file_name: str, version: str | None
) -> str:
    extension = Path(file_name).suffix or ".wav"
    version_segment = version or "current"
    return build_public_url(
        f"/api/public/campaign-audio/{campaign_id}/{campaign_id}-{version_segment}{extension}"
    )
