from __future__ import annotations

from collections.abc import Mapping

from django.utils import timezone
from rest_framework import serializers

from autodialer.models import (
    CallLog,
    Campaign,
    CampaignAudio,
    Contact,
    ContactImportFailure,
    ContactImportJob,
)
from autodialer.utils import build_versioned_media_url, normalize_bangladesh_number


def validate_contact_phone_number(value: str) -> str:
    normalized = normalize_bangladesh_number(value)
    if not normalized:
        raise serializers.ValidationError("Phone number is required.")
    if not normalized.isdigit():
        raise serializers.ValidationError("Phone number must contain digits only.")
    return normalized


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField()
    new_password = serializers.CharField()


class CampaignAudioSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = CampaignAudio
        fields = [  # noqa: RUF012
            "id",
            "audio_file",
            "original_name",
            "mime_type",
            "file_size",
            "file_url",
            "updated_at",
        ]
        extra_kwargs = {  # noqa: RUF012
            "audio_file": {"write_only": True},
            "original_name": {"read_only": True},
            "mime_type": {"read_only": True},
            "file_size": {"read_only": True},
            "updated_at": {"read_only": True},
        }

    def get_file_url(self, obj: CampaignAudio) -> str:
        version = str(int(obj.updated_at.timestamp())) if obj.updated_at else None
        return build_versioned_media_url(obj.audio_file.url, version)

    def validate_audio_file(self, value):
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if extension not in {"mp3", "wav"}:
            raise serializers.ValidationError("Only .mp3 and .wav files are allowed.")
        return value


class CampaignSerializer(serializers.ModelSerializer):
    audio = CampaignAudioSerializer(read_only=True)
    ongoing_calls = serializers.SerializerMethodField()
    contact_count = serializers.SerializerMethodField()
    completed_contacts = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [  # noqa: RUF012
            "id",
            "name",
            "status",
            "connect_to",
            "scheduled_at",
            "campaign_pace",
            "description",
            "billable_account",
            "caller_id",
            "metadata",
            "started_at",
            "paused_at",
            "finished_at",
            "last_dispatched_at",
            "audio",
            "ongoing_calls",
            "contact_count",
            "completed_contacts",
            "created_at",
            "updated_at",
        ]

    def get_ongoing_calls(self, obj: Campaign) -> int:
        return obj.call_logs.filter(
            status__in=[
                "trying",
                "ringing",
                "early",
                "connected",
                "held",
                "holding",
                "queued",
            ]
        ).count()

    def get_contact_count(self, obj: Campaign) -> int:
        return obj.contacts.count()

    def get_completed_contacts(self, obj: Campaign) -> int:
        return obj.contacts.filter(status=Contact.ContactStatus.CALLED).count()

    def validate_caller_id(self, value: str) -> str:
        return normalize_bangladesh_number(value)

    def validate(self, attrs):
        scheduled_at = attrs.get("scheduled_at")
        if scheduled_at and timezone.is_naive(scheduled_at):
            attrs["scheduled_at"] = timezone.make_aware(
                scheduled_at, timezone.get_default_timezone()
            )

        if attrs.get("scheduled_at") and attrs["scheduled_at"] > timezone.now():
            attrs["status"] = Campaign.CampaignStatus.SCHEDULED
        elif not attrs.get("status"):
            attrs["status"] = Campaign.CampaignStatus.NEW

        campaign_pace = attrs.get(
            "campaign_pace",
            getattr(self.instance, "campaign_pace", 0),
        )
        if campaign_pace < 1:
            raise serializers.ValidationError(
                {"campaign_pace": "Campaign pace must be at least 1 call per minute."}
            )

        return attrs


class ContactSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta:
        model = Contact
        fields = [  # noqa: RUF012
            "id",
            "campaign",
            "campaign_name",
            "phone_number",
            "name",
            "comments",
            "status",
            "metadata",
            "created_at",
            "updated_at",
        ]

    def validate_phone_number(self, value: str) -> str:
        return validate_contact_phone_number(value)

    def validate_campaign(self, value: Campaign) -> Campaign:
        profile = self.context["profile"]
        if value.owner_id != profile.id:
            raise serializers.ValidationError(
                "Selected campaign does not belong to the current user."
            )
        return value


class ContactImportRowSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    name = serializers.CharField(max_length=255)
    comments = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.ChoiceField(
        choices=Contact.ContactStatus.choices,
        required=False,
        default=Contact.ContactStatus.NEW,
    )

    def validate_phone_number(self, value: str) -> str:
        return validate_contact_phone_number(value)


class ContactImportFailureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactImportFailure
        fields = [  # noqa: RUF012
            "id",
            "row_number",
            "phone_number",
            "failure_reason",
            "row_data",
            "created_at",
        ]
        read_only_fields = fields


class ContactImportJobSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = ContactImportJob
        fields = [  # noqa: RUF012
            "id",
            "campaign",
            "campaign_name",
            "status",
            "original_filename",
            "total_rows",
            "processed_rows",
            "created_count",
            "failed_count",
            "cancel_requested",
            "error_message",
            "started_at",
            "completed_at",
            "progress_percent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_progress_percent(self, obj: ContactImportJob) -> int:
        if obj.total_rows <= 0:
            return 0
        return round(obj.processed_rows / obj.total_rows * 100)


class CallLogSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source="contact.name", read_only=True)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    campaign_started_at = serializers.DateTimeField(
        source="campaign.started_at", read_only=True
    )
    campaign_finished_at = serializers.DateTimeField(
        source="campaign.finished_at", read_only=True
    )
    derived_status = serializers.SerializerMethodField()

    class Meta:
        model = CallLog
        fields = [  # noqa: RUF012
            "id",
            "campaign_name",
            "campaign_started_at",
            "campaign_finished_at",
            "tracking_id",
            "external_call_id",
            "call_tag",
            "status",
            "derived_status",
            "account_id",
            "caller_id",
            "destination",
            "reason",
            "reason_code",
            "duration",
            "call_type",
            "connect_time",
            "start_time",
            "update_time",
            "playback_requested_at",
            "playback_completed_at",
            "contact_name",
            "request_payload",
            "response_payload",
            "webhook_payload",
        ]

    def get_derived_status(self, obj: CallLog) -> str:
        annotated_status = getattr(obj, "derived_status", None)
        if annotated_status:
            return annotated_status
        status_resolver = self.context.get("call_status_resolver")
        if callable(status_resolver):
            return status_resolver(obj)
        return "other"


class CampaignRestartSerializer(serializers.Serializer):
    restart_scope = serializers.ChoiceField(
        choices=[
            ("all", "All numbers"),
            ("not_answered", "Only not answered numbers"),
            ("exclude_invalid", "All numbers except invalid"),
        ]
    )
    run_mode = serializers.ChoiceField(
        choices=[("immediate", "Immediate"), ("scheduled", "Scheduled")]
    )
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        run_mode = attrs["run_mode"]
        scheduled_at = attrs.get("scheduled_at")
        if run_mode == "scheduled":
            if scheduled_at is None:
                raise serializers.ValidationError(
                    {"scheduled_at": "Scheduled time is required."}
                )
            if timezone.is_naive(scheduled_at):
                scheduled_at = timezone.make_aware(
                    scheduled_at, timezone.get_default_timezone()
                )
                attrs["scheduled_at"] = scheduled_at
            if scheduled_at <= timezone.now():
                raise serializers.ValidationError(
                    {"scheduled_at": "Scheduled time must be in the future."}
                )
        elif scheduled_at is not None:
            attrs["scheduled_at"] = None

        return attrs


class CampaignCallLogSummarySerializer(serializers.Serializer):
    campaign = serializers.DictField()
    filters = serializers.DictField()
    counts = serializers.DictField()
    rates = serializers.DictField()


def serialize_campaign_call_log_summary(
    *,
    campaign: Campaign,
    filters: Mapping[str, str],
    counts: Mapping[str, int],
    rates: Mapping[str, float],
) -> dict[str, object]:
    return CampaignCallLogSummarySerializer(
        {
            "campaign": {
                "id": str(campaign.id),
                "name": campaign.name,
                "status": campaign.status,
                "started_at": campaign.started_at,
                "finished_at": campaign.finished_at,
            },
            "filters": dict(filters),
            "counts": dict(counts),
            "rates": dict(rates),
        }
    ).data
