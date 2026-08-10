from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db.models import Case, CharField, Q, Value, When
from django.utils import timezone
from django.utils.text import get_valid_filename

if TYPE_CHECKING:
    from autodialer.models import CallLog, Campaign


CALL_STATUS_SUCCESS = "success"
CALL_STATUS_INVALID_NUMBER = "invalid_number"
CALL_STATUS_NOT_ANSWERED = "not_answered"
CALL_STATUS_OTHER = "other"

SUCCESS_REASONS = [
    "Answer Leg Disconnected Via Call Control API",
    "BYE Received",
]
INVALID_NUMBER_REASONS = ["Relayed Response: Auth Failed", "Auth Failed"]
RECEIVED_TIME_OFFSET = timedelta(hours=6)

CALL_LOG_EXPORT_HEADERS = [
    "Campaign Name",
    "Campaign Start Time",
    "Campaign Finish Time",
    "PortaOne Call ID",
    "Account ID",
    "Caller ID",
    "Destination",
    "Reason",
    "Reason Code",
    "Received Time",
    "Duration",
    "Playback Requested Time",
    "Playback Completed Time",
    "Status",
]


def build_derived_status_expression() -> Case:
    return Case(
        When(
            Q(reason__in=SUCCESS_REASONS) & Q(reason_code=487) & Q(duration__gt=0),
            then=Value(CALL_STATUS_SUCCESS),
        ),
        When(
            Q(reason="Temporarily Unavailable") & Q(reason_code=480) & Q(duration=0),
            then=Value(CALL_STATUS_NOT_ANSWERED),
        ),
        When(
            Q(reason__in=INVALID_NUMBER_REASONS) & Q(reason_code=403) & Q(duration=0),
            then=Value(CALL_STATUS_INVALID_NUMBER),
        ),
        default=Value(CALL_STATUS_OTHER),
        output_field=CharField(),
    )


def collect_latest_contact_statuses(call_logs: list[CallLog]) -> dict[object, str]:
    latest_statuses: dict[object, str] = {}
    for call_log in call_logs:
        contact_id = getattr(call_log, "contact_id", None)
        if not contact_id or contact_id in latest_statuses:
            continue
        latest_statuses[contact_id] = getattr(
            call_log, "derived_status", CALL_STATUS_OTHER
        )
    return latest_statuses


def format_call_log_label(value: str) -> str:
    return " ".join(
        part[:1].upper() + part[1:] for part in (value or "").split("_") if part
    )


def format_call_log_duration(seconds: int | None) -> str:
    if not seconds:
        return "0s"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    parts: list[str] = []

    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if remaining_seconds or not parts:
        parts.append(f"{remaining_seconds}s")

    return " ".join(parts)


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_default_timezone())
        return value

    normalized = value.strip().replace(" ", "T")
    normalized = re.sub(r"([+-]\d{2})$", r"\1:00", normalized)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


def _format_dhaka_datetime(
    value: datetime | str | None,
    *,
    empty_value: str,
    with_seconds: bool,
    extra_offset: timedelta | None = None,
) -> str:
    parsed = _coerce_datetime(value)
    if parsed is None:
        return empty_value
    if extra_offset is not None:
        parsed = parsed + extra_offset
    localized = timezone.localtime(parsed, timezone.get_default_timezone())
    pattern = "%d %b %Y, %I:%M:%S %p" if with_seconds else "%d %b %Y, %I:%M %p"
    return localized.strftime(pattern)


def format_call_log_datetime(value: datetime | str | None) -> str:
    return _format_dhaka_datetime(
        value,
        empty_value="Not scheduled",
        with_seconds=False,
    )


def format_call_log_datetime_with_seconds(value: datetime | str | None) -> str:
    return _format_dhaka_datetime(value, empty_value="-", with_seconds=True)


def format_call_log_received_time(value: datetime | str | None) -> str:
    return _format_dhaka_datetime(
        value,
        empty_value="-",
        with_seconds=True,
        extra_offset=RECEIVED_TIME_OFFSET,
    )


def build_call_log_export_filename(
    campaign: Campaign, created_at: datetime | None
) -> str:
    safe_campaign_name = get_valid_filename(campaign.name) or "campaign"
    timestamp = timezone.localtime(created_at or timezone.now()).strftime(
        "%Y%m%d-%H%M%S"
    )
    return f"{safe_campaign_name}-call-logs-{timestamp}.csv"


def build_call_log_export_row(call_log: CallLog) -> list[str]:
    reason_text = call_log.reason or "-"
    raw_status_label = format_call_log_label(call_log.status or "unknown") or "Unknown"
    derived_status = getattr(call_log, "derived_status", CALL_STATUS_OTHER)

    return [
        getattr(call_log.campaign, "name", "") if call_log.campaign else "",
        format_call_log_datetime_with_seconds(
            getattr(call_log.campaign, "started_at", None)
        ),
        format_call_log_datetime_with_seconds(
            getattr(call_log.campaign, "finished_at", None)
        ),
        call_log.external_call_id or "-",
        call_log.account_id or "-",
        call_log.caller_id or "-",
        call_log.destination or "-",
        f"{reason_text}\nCurrent status: {raw_status_label}",
        str(call_log.reason_code) if call_log.reason_code is not None else "-",
        format_call_log_received_time(call_log.connect_time),
        format_call_log_duration(call_log.duration),
        format_call_log_datetime(call_log.playback_requested_at),
        format_call_log_datetime(call_log.playback_completed_at),
        format_call_log_label(derived_status) or "Other",
    ]
