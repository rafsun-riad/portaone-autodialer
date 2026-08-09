from __future__ import annotations

import uuid
from pathlib import Path

from django.core.files.storage import default_storage
from django.db import models
from django.utils.text import get_valid_filename


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
        ordering = ["username"]  # noqa: RUF012

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
        ordering = ["-scheduled_at", "-created_at"]  # noqa: RUF012
        indexes = [  # noqa: RUF012
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "name"]),
            models.Index(fields=["owner", "scheduled_at"]),
        ]

    def __str__(self) -> str:
        return self.name


def campaign_audio_upload_to(instance: CampaignAudio, filename: str) -> str:
    parsed_name = Path(filename)
    extension = parsed_name.suffix.lower()
    safe_stem = (
        get_valid_filename(parsed_name.stem) or f"campaign_audio_{instance.campaign_id}"
    )
    base_directory = (
        f"campaign-audio/{instance.campaign.owner.username}/{instance.campaign_id}"
    )
    candidate_name = f"{safe_stem}{extension}"
    candidate_path = f"{base_directory}/{candidate_name}"
    duplicate_counter = 2

    while default_storage.exists(candidate_path):
        candidate_name = f"{safe_stem}-{duplicate_counter}{extension}"
        candidate_path = f"{base_directory}/{candidate_name}"
        duplicate_counter += 1

    return candidate_path


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
        ordering = ["-updated_at"]  # noqa: RUF012

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
        ordering = ["-created_at"]  # noqa: RUF012
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["owner", "campaign", "phone_number"],
                name="unique_contact_per_campaign_phone",
            )
        ]
        indexes = [  # noqa: RUF012
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["owner", "phone_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone_number})"


def contact_import_upload_to(instance: ContactImportJob, filename: str) -> str:
    parsed_name = Path(filename)
    extension = parsed_name.suffix.lower()
    safe_stem = get_valid_filename(parsed_name.stem) or f"contact_import_{instance.id}"
    return (
        "contact-imports/"
        f"{instance.owner.username}/{instance.campaign_id}/{instance.id}/"
        f"{safe_stem}{extension}"
    )


class ContactImportJob(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PREPARING = "preparing", "Preparing"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    owner = models.ForeignKey(
        ExternalUserProfile,
        on_delete=models.CASCADE,
        related_name="contact_import_jobs",
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="contact_import_jobs",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    csv_file = models.FileField(
        upload_to=contact_import_upload_to,
        max_length=255,
    )
    original_filename = models.CharField(max_length=255, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    cancel_requested = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]  # noqa: RUF012
        indexes = [  # noqa: RUF012
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "campaign", "status"]),
        ]

    def __str__(self) -> str:
        return f"Import {self.id} for {self.campaign}"


class ContactImportFailure(TimestampedModel):
    job = models.ForeignKey(
        ContactImportJob,
        on_delete=models.CASCADE,
        related_name="failures",
    )
    row_number = models.PositiveIntegerField()
    phone_number = models.CharField(max_length=32, blank=True)
    row_data = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField()

    class Meta:
        ordering = ["row_number", "created_at"]  # noqa: RUF012
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["job", "row_number"],
                name="unique_contact_import_failure_row",
            )
        ]

    def __str__(self) -> str:
        return f"Import failure row {self.row_number}"


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
        ordering = ["-created_at"]  # noqa: RUF012
        indexes = [  # noqa: RUF012
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["contact", "status"]),
            models.Index(fields=["tracking_id"]),
            models.Index(fields=["external_call_id"]),
        ]

    def __str__(self) -> str:
        return self.tracking_id or self.external_call_id or f"call-{self.pk}"
