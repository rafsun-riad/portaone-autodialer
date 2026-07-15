from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from autodialer.models import CallLog, Campaign, CampaignAudio, Contact
from autodialer.utils import normalize_bangladesh_number


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
        fields = [
            "id",
            "audio_file",
            "original_name",
            "mime_type",
            "file_size",
            "file_url",
            "updated_at",
        ]
        extra_kwargs = {"audio_file": {"write_only": True}}

    def get_file_url(self, obj: CampaignAudio) -> str:
        request = self.context.get("request")
        if request is None:
            return obj.audio_file.url
        return request.build_absolute_uri(obj.audio_file.url)

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
        fields = [
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

        if attrs.get("campaign_pace", 0) < 1:
            raise serializers.ValidationError(
                {"campaign_pace": "Campaign pace must be at least 1 call per minute."}
            )

        return attrs


class ContactSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta:
        model = Contact
        fields = [
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
        normalized = normalize_bangladesh_number(value)
        if not normalized:
            raise serializers.ValidationError("Phone number is required.")
        return normalized

    def validate_campaign(self, value: Campaign) -> Campaign:
        profile = self.context["profile"]
        if value.owner_id != profile.id:
            raise serializers.ValidationError(
                "Selected campaign does not belong to the current user."
            )
        return value


class CallLogSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source="contact.name", read_only=True)

    class Meta:
        model = CallLog
        fields = [
            "id",
            "tracking_id",
            "external_call_id",
            "call_tag",
            "status",
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
