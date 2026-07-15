from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from autodialer.models import Campaign, Contact
from autodialer.services.workflows import (
    dispatch_campaign_calls,
    maybe_finish_campaign,
    play_campaign_audio,
)


@shared_task(name="autodialer.tasks.activate_due_campaigns")
def activate_due_campaigns() -> int:
    now = timezone.now()
    activated_count = 0
    due_campaigns = Campaign.objects.filter(
        status__in=[
            Campaign.CampaignStatus.NEW,
            Campaign.CampaignStatus.SCHEDULED,
            Campaign.CampaignStatus.OVERDUE,
        ],
        scheduled_at__isnull=False,
        scheduled_at__lte=now,
    ).select_related("owner")

    for campaign in due_campaigns:
        has_audio = hasattr(campaign, "audio")
        has_contacts = campaign.contacts.filter(
            status__in=[Contact.ContactStatus.NEW, Contact.ContactStatus.ACTIVE]
        ).exists()
        if not has_audio or not has_contacts or not campaign.owner.access_token:
            if campaign.status != Campaign.CampaignStatus.OVERDUE:
                campaign.status = Campaign.CampaignStatus.OVERDUE
                campaign.save(update_fields=["status", "updated_at"])
            continue

        campaign.status = Campaign.CampaignStatus.PROCESSING
        campaign.started_at = campaign.started_at or now
        campaign.save(update_fields=["status", "started_at", "updated_at"])
        dispatch_campaign_calls(campaign)
        activated_count += 1

    return activated_count


@shared_task(name="autodialer.tasks.dispatch_campaign_calls_task")
def dispatch_campaign_calls_task(campaign_id: int) -> list[int]:
    campaign = Campaign.objects.select_related("owner").filter(pk=campaign_id).first()
    if campaign is None:
        return []
    return dispatch_campaign_calls(campaign)


@shared_task(name="autodialer.tasks.pump_processing_campaigns")
def pump_processing_campaigns() -> int:
    processed = 0
    for campaign in Campaign.objects.filter(
        status=Campaign.CampaignStatus.PROCESSING
    ).select_related("owner"):
        dispatch_campaign_calls(campaign)
        maybe_finish_campaign(campaign)
        processed += 1
    return processed


@shared_task(name="autodialer.tasks.play_campaign_audio_task")
def play_campaign_audio_task(call_log_id: int) -> None:
    from autodialer.models import CallLog

    call_log = (
        CallLog.objects.select_related("owner", "campaign")
        .filter(pk=call_log_id)
        .first()
    )
    if call_log is None:
        return
    play_campaign_audio(call_log)
