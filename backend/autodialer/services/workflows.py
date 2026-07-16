from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from autodialer.models import (
    CallLog,
    Campaign,
    CampaignAudio,
    Contact,
    ExternalUserProfile,
)
from autodialer.services.external_api import ExternalSystemClient, ExternalSystemError
from autodialer.utils import (
    build_public_playback_audio_url,
    build_public_url,
    normalize_bangladesh_number,
    parse_external_datetime,
)

ACTIVE_CALL_STATES = {
    "trying",
    "ringing",
    "early",
    "connected",
    "held",
    "holding",
    "queued",
    "dequeued",
    "transferred",
    "parked",
}

logger = logging.getLogger(__name__)


def unwrap_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    wrapped_payload = payload.get("call_info")
    if isinstance(wrapped_payload, dict):
        return wrapped_payload
    return payload


def sync_customer_profile(
    username: str, auth_payload: dict[str, Any]
) -> ExternalUserProfile:
    client = ExternalSystemClient(access_token=auth_payload["access_token"])
    customer_response = client.get_customer_info()
    customer_info = customer_response.get("customer_info", {})
    i_customer = customer_info.get("i_customer")

    with transaction.atomic():
        profile = (
            ExternalUserProfile.objects.select_for_update()
            .filter(Q(username=username) | Q(i_customer=i_customer))
            .order_by("pk")
            .first()
        )

        if profile is None:
            profile = ExternalUserProfile(username=username)

        profile.username = username
        profile.i_customer = i_customer
        profile.external_data = customer_info
        profile.access_token = auth_payload.get("access_token", "")
        profile.refresh_token = auth_payload.get("refresh_token", "")
        profile.session_id = auth_payload.get("session_id", "")
        profile.token_expires_at = parse_external_datetime(
            auth_payload.get("expires_at")
        )
        profile.last_synced_at = timezone.now()
        profile.save()

    return profile


def list_external_accounts(profile: ExternalUserProfile) -> dict[str, Any]:
    client = ExternalSystemClient(access_token=profile.access_token)
    response = client.get_account_list(profile.i_customer)
    account_list = response.get("account_list", [])
    options: list[dict[str, Any]] = []

    for account in account_list:
        connect_to = str(account.get("id", ""))
        caller_source = account.get("did_number") or account.get("id") or ""
        options.append(
            {
                "connect_to": connect_to,
                "billable_account": connect_to,
                "caller_id": normalize_bangladesh_number(str(caller_source)),
                "label": connect_to,
                "account": account,
            }
        )

    return {"account_list": account_list, "options": options}


def resolve_campaign_status(scheduled_at, current_status: str | None = None) -> str:
    if scheduled_at and scheduled_at > timezone.now():
        return Campaign.CampaignStatus.SCHEDULED
    if current_status in Campaign.CampaignStatus.values:
        return current_status
    return Campaign.CampaignStatus.NEW


def reset_campaign_runtime_state(
    campaign: Campaign,
    *,
    reset_contacts: bool = False,
    now=None,
) -> None:
    now = now or timezone.now()

    campaign.call_logs.filter(status__in=ACTIVE_CALL_STATES).update(
        status="terminated",
        reason="Campaign state reset",
        update_time=now,
        updated_at=now,
    )

    if reset_contacts:
        campaign.contacts.exclude(status=Contact.ContactStatus.INVALID).update(
            status=Contact.ContactStatus.NEW,
            updated_at=now,
        )


def apply_campaign_action(campaign: Campaign, action_name: str) -> bool:
    now = timezone.now()
    should_dispatch = False

    if action_name == "start":
        if campaign.status not in {
            Campaign.CampaignStatus.NEW,
            Campaign.CampaignStatus.SCHEDULED,
            Campaign.CampaignStatus.OVERDUE,
        }:
            raise ValidationError(
                {"detail": "Only new, scheduled, or overdue campaigns can be started."}
            )
        reset_campaign_runtime_state(campaign, reset_contacts=True, now=now)
        campaign.status = Campaign.CampaignStatus.PROCESSING
        campaign.started_at = campaign.started_at or now
        campaign.finished_at = None
        campaign.paused_at = None
        should_dispatch = True
    elif action_name == "stop":
        reset_campaign_runtime_state(campaign, reset_contacts=False, now=now)
        campaign.status = Campaign.CampaignStatus.CANCELED
        campaign.finished_at = now
    elif action_name == "pause":
        if campaign.status != Campaign.CampaignStatus.PROCESSING:
            raise ValidationError(
                {"detail": "Only processing campaigns can be paused."}
            )
        campaign.status = Campaign.CampaignStatus.PAUSED
        campaign.paused_at = now
    elif action_name == "resume":
        if campaign.status != Campaign.CampaignStatus.PAUSED:
            raise ValidationError({"detail": "Only paused campaigns can be resumed."})
        campaign.status = Campaign.CampaignStatus.PROCESSING
        campaign.paused_at = None
        should_dispatch = True
    elif action_name == "restart":
        if campaign.status not in {
            Campaign.CampaignStatus.FINISHED,
            Campaign.CampaignStatus.CANCELED,
        }:
            raise ValidationError(
                {"detail": "Only finished or canceled campaigns can be restarted."}
            )
        reset_campaign_runtime_state(campaign, reset_contacts=True, now=now)
        campaign.status = Campaign.CampaignStatus.PROCESSING
        campaign.started_at = now
        campaign.finished_at = None
        campaign.paused_at = None
        should_dispatch = True
    else:
        raise ValidationError({"detail": "Unsupported campaign action."})

    campaign.save(
        update_fields=[
            "status",
            "started_at",
            "paused_at",
            "finished_at",
            "updated_at",
        ]
    )
    return should_dispatch


def build_state_callback_url() -> str:
    return build_public_url("/api/webhooks/calls/state/")


def build_playback_callback_url() -> str:
    return build_public_url("/api/webhooks/calls/playback/")


def originate_call_for_contact(campaign: Campaign, contact: Contact) -> CallLog:
    if not campaign.owner.access_token:
        raise ValidationError(
            {"detail": "This user does not have an active PortaOne session."}
        )

    request_params = {
        "account_id": campaign.connect_to,
        "caller_id": campaign.caller_id,
        "destination": contact.phone_number,
        "state_info_callback": build_state_callback_url(),
        "state_info_events": list(settings.DEFAULT_CALL_STATE_EVENTS),
    }

    client = ExternalSystemClient(access_token=campaign.owner.access_token)

    try:
        response = client.originate_call(request_params)
        call_data = response.get("call", {})
        call_log = CallLog.objects.create(
            owner=campaign.owner,
            campaign=campaign,
            contact=contact,
            external_call_id=call_data.get("id", ""),
            tracking_id=response.get("tracking_id"),
            status="trying",
            account_id=campaign.connect_to,
            caller_id=campaign.caller_id,
            destination=contact.phone_number,
            request_payload=request_params,
            response_payload=response,
        )
        contact.status = Contact.ContactStatus.QUEUED
        contact.save(update_fields=["status", "updated_at"])
        return call_log
    except ExternalSystemError as exc:
        call_log = CallLog.objects.create(
            owner=campaign.owner,
            campaign=campaign,
            contact=contact,
            status="failed",
            account_id=campaign.connect_to,
            caller_id=campaign.caller_id,
            destination=contact.phone_number,
            request_payload=request_params,
            response_payload=exc.payload,
            reason=exc.payload.get("faultstring", str(exc)),
        )
        contact.status = Contact.ContactStatus.FAILED
        contact.save(update_fields=["status", "updated_at"])
        return call_log


def maybe_finish_campaign(campaign: Campaign | None) -> None:
    if campaign is None:
        return

    has_pending_contacts = campaign.contacts.filter(
        status__in=[
            Contact.ContactStatus.NEW,
            Contact.ContactStatus.ACTIVE,
            Contact.ContactStatus.QUEUED,
        ]
    ).exists()
    has_active_calls = campaign.call_logs.filter(status__in=ACTIVE_CALL_STATES).exists()
    if not has_pending_contacts and not has_active_calls:
        campaign.status = Campaign.CampaignStatus.FINISHED
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=["status", "finished_at", "updated_at"])


def dispatch_campaign_calls(campaign: Campaign) -> list[int]:
    if campaign.status != Campaign.CampaignStatus.PROCESSING:
        return []

    active_count = campaign.call_logs.filter(status__in=ACTIVE_CALL_STATES).count()
    available_slots = max(campaign.campaign_pace - active_count, 0)

    if available_slots == 0:
        return []

    contacts = list(
        campaign.contacts.filter(
            status__in=[Contact.ContactStatus.NEW, Contact.ContactStatus.ACTIVE]
        ).order_by("id")[:available_slots]
    )

    if not contacts:
        maybe_finish_campaign(campaign)
        return []

    dispatched_ids: list[int] = []
    for contact in contacts:
        call_log = originate_call_for_contact(campaign, contact)
        dispatched_ids.append(call_log.pk)

    campaign.last_dispatched_at = timezone.now()
    campaign.save(update_fields=["last_dispatched_at", "updated_at"])
    return dispatched_ids


def handle_state_webhook(payload: dict[str, Any]) -> CallLog:
    payload = unwrap_webhook_payload(payload)
    tracking_id = payload.get("tracking_id")
    call_info = payload.get("call", {})
    call_log = (
        CallLog.objects.select_related("campaign", "contact", "owner")
        .filter(
            Q(tracking_id=tracking_id)
            | Q(external_call_id=call_info.get("id"))
            | Q(previous_tracking_id=payload.get("previous_tracking_id"))
        )
        .order_by("-id")
        .first()
    )

    if call_log is None:
        call_log = CallLog.objects.create(
            tracking_id=tracking_id,
            external_call_id=call_info.get("id", ""),
            status=payload.get("state", ""),
            webhook_payload=payload,
        )

    call_log.external_call_id = call_info.get("id", call_log.external_call_id)
    call_log.call_tag = call_info.get("tag", call_log.call_tag)
    call_log.status = payload.get("state", call_log.status)
    call_log.previous_tracking_id = payload.get(
        "previous_tracking_id", call_log.previous_tracking_id
    )
    call_log.reason = payload.get("reason", call_log.reason)
    call_log.reason_code = payload.get("reason_code", call_log.reason_code)
    call_log.duration = payload.get("duration") or call_log.duration
    call_log.call_type = payload.get("type", call_log.call_type)
    call_log.start_time = (
        parse_external_datetime(payload.get("start_time")) or call_log.start_time
    )
    call_log.update_time = (
        parse_external_datetime(payload.get("update_time")) or timezone.now()
    )
    call_log.connect_time = (
        parse_external_datetime(payload.get("connect_time")) or call_log.connect_time
    )
    call_log.webhook_payload = payload
    call_log.save()

    if call_log.contact_id and call_log.status == "terminated":
        if call_log.connect_time or call_log.duration:
            call_log.contact.status = Contact.ContactStatus.CALLED
        else:
            call_log.contact.status = Contact.ContactStatus.FAILED
        call_log.contact.save(update_fields=["status", "updated_at"])

    if call_log.campaign and call_log.status == "terminated":
        maybe_finish_campaign(call_log.campaign)

    return call_log


def play_campaign_audio(call_log: CallLog) -> None:
    if not call_log.campaign_id or not call_log.owner_id:
        return

    audio = CampaignAudio.objects.filter(campaign=call_log.campaign).first()
    if audio is None or not call_log.external_call_id or not call_log.call_tag:
        return

    if call_log.playback_requested_at is not None:
        return

    client = ExternalSystemClient(access_token=call_log.owner.access_token)
    callback_url = build_playback_callback_url()
    media_version = str(int(audio.updated_at.timestamp())) if audio.updated_at else None
    media_url = build_public_playback_audio_url(
        call_log.campaign_id,
        audio.original_name or audio.audio_file.name,
        media_version,
    )
    playback_params = {
        "call": {"id": call_log.external_call_id, "tag": call_log.call_tag},
        "callback_on_events": [
            "prompt_playback_interrupted",
            "prompt_playback_completed",
        ],
        "callback_url": callback_url,
        "interrupt_playback_on_input": "Y",
        "repeat": 1,
        "url": media_url,
    }

    logger.warning(
        "Playback request prepared for call %s with callback_url=%s media_url=%s",
        call_log.external_call_id,
        callback_url,
        media_url,
    )

    response_payload = dict(call_log.response_payload or {})
    response_payload["playback_request"] = playback_params

    try:
        playback_response = client.play_audio(playback_params)
    except ExternalSystemError as exc:
        response_payload["playback_error"] = exc.payload or {"message": str(exc)}
        call_log.response_payload = response_payload
        call_log.reason = (
            exc.payload.get("faultstring", str(exc)) if exc.payload else str(exc)
        )
        call_log.save(update_fields=["response_payload", "reason", "updated_at"])
        logger.exception(
            "Playback request failed for call %s with callback_url=%s media_url=%s",
            call_log.external_call_id,
            callback_url,
            media_url,
        )
        return

    response_payload["playback_response"] = playback_response
    call_log.response_payload = response_payload
    call_log.playback_requested_at = timezone.now()
    call_log.save(
        update_fields=["response_payload", "playback_requested_at", "updated_at"]
    )
    logger.warning(
        "Playback request accepted for call %s with callback_url=%s media_url=%s",
        call_log.external_call_id,
        callback_url,
        media_url,
    )


def handle_playback_webhook(payload: dict[str, Any]) -> CallLog | None:
    payload = unwrap_webhook_payload(payload)
    tracking_id = payload.get("tracking_id")
    call_info = payload.get("call", {})
    call_log = (
        CallLog.objects.filter(
            Q(tracking_id=tracking_id) | Q(external_call_id=call_info.get("id"))
        )
        .order_by("-id")
        .first()
    )
    if call_log is None:
        return None

    serialized_payload = json.dumps(payload)
    if "prompt_playback_completed" in serialized_payload:
        call_log.playback_completed_at = timezone.now()
        call_log.save(update_fields=["playback_completed_at", "updated_at"])
    return call_log
