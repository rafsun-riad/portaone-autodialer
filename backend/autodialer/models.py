from __future__ import annotations

from pathlib import Path

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ExternalUserProfile(TimestampedModel):
    username = models.CharField(max_length=150, unique=True)
    i_customer = models.BigIntegerField(unique=True, null=True, blank=True)
    external_data = models.JSONField(default=dict, blank=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.CharField(max_length=255, blank=True)
    session_id = models.CharField(max_length=255, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username


class Campaign(TimestampedModel):
    class CampaignStatus(models.TextChoices):
        NEW = "new", "New"
        SCHEDULED = "scheduled", "Scheduled"
        PROCESSING = "processing", "Processing"
        PAUSED = "paused", "Paused"
        FINISHED = "finished", "Finished"
        OVERDUE = "overdue", "Overdue"
        CANCELED = "canceled", "Canceled"

    owner = models.ForeignKey(
        ExternalUserProfile,
        on_delete=models.CASCADE,
        related_name="campaigns",
    )
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=CampaignStatus.choices,
        default=CampaignStatus.NEW,
        db_index=True,
    )
    connect_to = models.CharField(max_length=128)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    campaign_pace = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    billable_account = models.CharField(max_length=128)
    caller_id = models.CharField(max_length=128)
    metadata = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-scheduled_at", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "name"]),
            models.Index(fields=["owner", "scheduled_at"]),
        ]

    def __str__(self) -> str:
        return self.name


def campaign_audio_upload_to(instance: "CampaignAudio", filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return (
        f"campaign-audio/{instance.campaign.owner.username}/"
        f"{instance.campaign_id}/{instance.campaign_id}{extension}"
    )


class CampaignAudio(TimestampedModel):
    campaign = models.OneToOneField(
        Campaign,
        on_delete=models.CASCADE,
        related_name="audio",
    )
    audio_file = models.FileField(upload_to=campaign_audio_upload_to)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=128, blank=True)
    file_size = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.original_name


class Contact(TimestampedModel):
    class ContactStatus(models.TextChoices):
        NEW = "new", "New"
        ACTIVE = "active", "Active"
        QUEUED = "queued", "Queued"
        CALLED = "called", "Called"
        FAILED = "failed", "Failed"
        PAUSED = "paused", "Paused"
        INVALID = "invalid", "Invalid"

    owner = models.ForeignKey(
        ExternalUserProfile,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    phone_number = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=255)
    comments = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=ContactStatus.choices,
        default=ContactStatus.NEW,
        db_index=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "campaign", "phone_number"],
                name="unique_contact_per_campaign_phone",
            )
        ]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["owner", "phone_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone_number})"


class CallLog(TimestampedModel):
    owner = models.ForeignKey(
        ExternalUserProfile,
        on_delete=models.SET_NULL,
        related_name="call_logs",
        null=True,
        blank=True,
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.SET_NULL,
        related_name="call_logs",
        null=True,
        blank=True,
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        related_name="call_logs",
        null=True,
        blank=True,
    )
    external_call_id = models.CharField(max_length=128, blank=True, db_index=True)
    call_tag = models.CharField(max_length=128, blank=True)
    tracking_id = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=32, blank=True, db_index=True)
    account_id = models.CharField(max_length=128, blank=True)
    caller_id = models.CharField(max_length=128, blank=True)
    destination = models.CharField(max_length=32, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    webhook_payload = models.JSONField(default=dict, blank=True)
    previous_tracking_id = models.CharField(max_length=128, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    reason_code = models.IntegerField(null=True, blank=True)
    duration = models.PositiveIntegerField(default=0)
    call_type = models.CharField(max_length=64, blank=True)
    connect_time = models.DateTimeField(null=True, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    update_time = models.DateTimeField(null=True, blank=True)
    playback_requested_at = models.DateTimeField(null=True, blank=True)
    playback_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["contact", "status"]),
            models.Index(fields=["tracking_id"]),
            models.Index(fields=["external_call_id"]),
        ]

    def __str__(self) -> str:
        return self.tracking_id or self.external_call_id or f"call-{self.pk}"
