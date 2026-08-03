from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from uuid import UUID

from django.db.models import Case, CharField, Q, Value, When
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from autodialer.models import (
    CallLog,
    Campaign,
    CampaignAudio,
    Contact,
    ExternalUserProfile,
)
from autodialer.serializers import (
    CallLogSerializer,
    CampaignAudioSerializer,
    CampaignRestartSerializer,
    CampaignSerializer,
    ChangePasswordSerializer,
    ContactSerializer,
    LoginSerializer,
    serialize_campaign_call_log_summary,
)
from autodialer.services.external_api import ExternalSystemClient, ExternalSystemError
from autodialer.services.webhook_logs import append_webhook_payload
from autodialer.services.workflows import (
    ACTIVE_CALL_STATES,
    apply_campaign_action,
    handle_playback_webhook,
    handle_state_webhook,
    is_internal_outgoing_leg,
    list_external_accounts,
    reset_campaign_runtime_state,
    sync_customer_profile,
)
from autodialer.tasks import dispatch_campaign_calls_task, play_campaign_audio_task


class CampaignPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class ContactPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class CallLogPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 100


CALL_STATUS_SUCCESS = "success"
CALL_STATUS_INVALID_NUMBER = "invalid_number"
CALL_STATUS_NOT_ANSWERED = "not_answered"
CALL_STATUS_OTHER = "other"

SUCCESS_REASONS = [
    "Answer Leg Disconnected Via Call Control API",
    "BYE Received",
]
INVALID_NUMBER_REASONS = ["Relayed Response: Auth Failed", "Auth Failed"]


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


def collect_latest_contact_statuses(call_logs: Iterable[CallLog]) -> dict[str, str]:
    latest_statuses: dict[str, str] = {}
    for call_log in call_logs:
        if call_log.contact_id is None or call_log.contact_id in latest_statuses:
            continue
        latest_statuses[call_log.contact_id] = getattr(
            call_log, "derived_status", CALL_STATUS_OTHER
        )
    return latest_statuses


class ExternalSessionMixin:
    profile: ExternalUserProfile | None = None
    request_access_token: str | None = None

    def get_profile(self) -> ExternalUserProfile:
        if self.profile is not None:
            return self.profile

        username = self.request.headers.get("X-Portal-Username", "").strip()
        authorization = self.request.headers.get("Authorization", "")
        if not username or not authorization.startswith("Bearer "):
            raise AuthenticationFailed("Missing PortaOne session headers.")

        access_token = authorization.removeprefix("Bearer ").strip()
        self.request_access_token = access_token
        try:
            self.profile = ExternalUserProfile.objects.get(username=username)
        except ExternalUserProfile.DoesNotExist as exc:
            raise AuthenticationFailed("Invalid PortaOne session.") from exc

        self.profile.access_token = access_token
        return self.profile

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["profile"] = self.get_profile()
        return context


class LoginView(APIView):
    parser_classes = [JSONParser]  # noqa: RUF012

    @staticmethod
    def _external_error_response(exc: ExternalSystemError):
        payload = exc.payload or {}
        requires_password_change = (
            payload.get("faultcode") == "Server.Session.alert_You_must_change_password"
        )
        return Response(
            {
                "message": payload.get("faultstring", str(exc)),
                "requires_password_change": requires_password_change,
                "faultcode": payload.get("faultcode"),
                "payload": payload,
            },
            status=status.HTTP_409_CONFLICT
            if requires_password_change
            else exc.status_code,
        )

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]
        client = ExternalSystemClient()

        try:
            auth_payload = client.login(username=username, password=password)
        except ExternalSystemError as exc:
            return self._external_error_response(exc)

        try:
            profile = sync_customer_profile(
                username=username, auth_payload=auth_payload
            )
        except ExternalSystemError as exc:
            return self._external_error_response(exc)

        return Response(
            {
                "profile": {
                    "username": profile.username,
                    "i_customer": profile.i_customer,
                    "external_data": profile.external_data,
                    "last_synced_at": profile.last_synced_at,
                },
                "auth": auth_payload,
            }
        )


class ChangePasswordView(APIView):
    parser_classes = [JSONParser]  # noqa: RUF012

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = ExternalSystemClient()

        try:
            payload = client.change_password(**serializer.validated_data)
        except ExternalSystemError as exc:
            return Response(exc.payload, status=exc.status_code)

        return Response(payload)


class MeView(ExternalSessionMixin, APIView):
    def get(self, request):
        profile = self.get_profile()
        try:
            profile = sync_customer_profile(
                username=profile.username,
                auth_payload={
                    "access_token": profile.access_token,
                    "refresh_token": profile.refresh_token,
                    "session_id": profile.session_id,
                    "expires_at": profile.token_expires_at.isoformat()
                    if profile.token_expires_at
                    else None,
                },
            )
        except ExternalSystemError as exc:
            return LoginView._external_error_response(exc)

        return Response(
            {
                "username": profile.username,
                "i_customer": profile.i_customer,
                "external_data": profile.external_data,
                "last_synced_at": profile.last_synced_at,
            }
        )


class AccountOptionsView(ExternalSessionMixin, APIView):
    def get(self, request):
        profile = self.get_profile()
        return Response(list_external_accounts(profile))


class CampaignViewSet(ExternalSessionMixin, viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    pagination_class = CampaignPagination

    def get_queryset(self):
        profile = self.get_profile()
        queryset = (
            Campaign.objects.filter(owner=profile)
            .prefetch_related("audio")
            .order_by("-scheduled_at", "-created_at")
        )
        search = self.request.query_params.get("search", "").strip()
        status_filter = self.request.query_params.get("status", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def perform_create(self, serializer):
        serializer.save(owner=self.get_profile())

    def perform_update(self, serializer):
        campaign = serializer.save(owner=self.get_profile())

        if campaign.scheduled_at and campaign.scheduled_at > timezone.now():
            reset_campaign_runtime_state(campaign, reset_contacts=True)
            campaign.status = Campaign.CampaignStatus.SCHEDULED
            campaign.started_at = None
            campaign.paused_at = None
            campaign.finished_at = None
            campaign.last_dispatched_at = None
            campaign.save(
                update_fields=[
                    "status",
                    "started_at",
                    "paused_at",
                    "finished_at",
                    "last_dispatched_at",
                    "updated_at",
                ]
            )


class CampaignActionView(ExternalSessionMixin, APIView):
    def post(self, request, campaign_id: UUID, action_name: str):
        campaign = Campaign.objects.filter(
            owner=self.get_profile(), pk=campaign_id
        ).first()
        if campaign is None:
            raise ValidationError({"detail": "Campaign not found."})

        should_dispatch = apply_campaign_action(campaign, action_name)
        if should_dispatch:
            dispatch_campaign_calls_task.delay(str(campaign.id))

        return Response(CampaignSerializer(campaign, context={"request": request}).data)


class CampaignAudioView(ExternalSessionMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]  # noqa: RUF012

    def get_campaign(self, campaign_id: UUID) -> Campaign:
        campaign = Campaign.objects.filter(
            owner=self.get_profile(), pk=campaign_id
        ).first()
        if campaign is None:
            raise ValidationError({"detail": "Campaign not found."})
        return campaign

    def get(self, request, campaign_id: UUID):
        campaign = self.get_campaign(campaign_id)
        audio = CampaignAudio.objects.filter(campaign=campaign).first()
        if audio is None:
            return Response({"audio": None})
        return Response(
            {"audio": CampaignAudioSerializer(audio, context={"request": request}).data}
        )

    def post(self, request, campaign_id: UUID):
        campaign = self.get_campaign(campaign_id)
        instance = CampaignAudio.objects.filter(campaign=campaign).first()
        serializer = CampaignAudioSerializer(
            instance=instance, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        if instance and instance.audio_file:
            instance.audio_file.delete(save=False)
        audio = serializer.save(
            campaign=campaign,
            original_name=serializer.validated_data["audio_file"].name,
            mime_type=serializer.validated_data["audio_file"].content_type or "",
            file_size=serializer.validated_data["audio_file"].size,
        )
        return Response(
            CampaignAudioSerializer(audio, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, campaign_id: UUID):
        campaign = self.get_campaign(campaign_id)
        audio = CampaignAudio.objects.filter(campaign=campaign).first()
        if audio is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        audio.audio_file.delete(save=False)
        audio.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicCampaignAudioPlaybackView(APIView):
    authentication_classes = []  # noqa: RUF012
    permission_classes = []  # noqa: RUF012

    def get(self, request, campaign_id: UUID, versioned_name: str):
        audio = CampaignAudio.objects.filter(campaign_id=campaign_id).first()
        if audio is None or not audio.audio_file:
            raise Http404("Campaign audio not found.")

        audio.audio_file.open("rb")
        response = FileResponse(
            audio.audio_file,
            content_type=audio.mime_type or "application/octet-stream",
        )
        response["Content-Disposition"] = f'inline; filename="{audio.original_name}"'
        return response


class ContactViewSet(ExternalSessionMixin, viewsets.ModelViewSet):
    serializer_class = ContactSerializer
    pagination_class = ContactPagination

    def get_queryset(self):
        profile = self.get_profile()
        queryset = (
            Contact.objects.filter(owner=profile)
            .select_related("campaign")
            .order_by("-created_at")
        )

        search = self.request.query_params.get("search", "").strip()
        name = self.request.query_params.get("name", "").strip()
        phone_number = self.request.query_params.get("phone_number", "").strip()
        campaign_id = self.request.query_params.get("campaign", "").strip()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(campaign__name__icontains=search)
            )
        if name:
            queryset = queryset.filter(name__icontains=name)
        if phone_number:
            queryset = queryset.filter(phone_number__icontains=phone_number)
        if campaign_id:
            queryset = queryset.filter(campaign_id=campaign_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(owner=self.get_profile())

    def perform_update(self, serializer):
        serializer.save(owner=self.get_profile())


class BulkContactUploadView(ExternalSessionMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]  # noqa: RUF012

    def post(self, request):
        profile = self.get_profile()
        campaign_id = request.data.get("campaign")
        upload = request.data.get("file")
        if not campaign_id or upload is None:
            raise ValidationError({"detail": "Campaign and CSV file are required."})

        campaign = Campaign.objects.filter(owner=profile, pk=campaign_id).first()
        if campaign is None:
            raise ValidationError({"detail": "Campaign not found."})

        decoded_file = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded_file))
        created_count = 0
        updated_count = 0
        errors: list[dict[str, str]] = []

        for row_number, row in enumerate(reader, start=2):
            serializer = ContactSerializer(
                data={
                    "campaign": campaign.id,
                    "phone_number": row.get("phone_number", ""),
                    "name": row.get("name", ""),
                    "comments": row.get("comments", ""),
                    "status": row.get("status", Contact.ContactStatus.NEW),
                },
                context={"profile": profile},
            )
            if not serializer.is_valid():
                errors.append({"row": str(row_number), "errors": serializer.errors})
                continue

            phone_number = serializer.validated_data["phone_number"]
            _, created = Contact.objects.update_or_create(
                owner=profile,
                campaign=campaign,
                phone_number=phone_number,
                defaults={
                    "name": serializer.validated_data["name"],
                    "comments": serializer.validated_data.get("comments", ""),
                    "status": serializer.validated_data.get(
                        "status", Contact.ContactStatus.NEW
                    ),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        return Response(
            {
                "created_count": created_count,
                "updated_count": updated_count,
                "errors": errors,
            }
        )


class CampaignCallLogView(
    ExternalSessionMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = CallLogSerializer
    pagination_class = CallLogPagination

    def get_campaign(self) -> Campaign:
        profile = self.get_profile()
        campaign = Campaign.objects.filter(
            owner=profile, pk=self.kwargs["campaign_id"]
        ).first()
        if campaign is None:
            raise ValidationError({"detail": "Campaign not found."})
        return campaign

    def get_queryset(self):
        profile = self.get_profile()
        campaign_id = self.kwargs["campaign_id"]
        queryset = (
            CallLog.objects.filter(owner=profile, campaign_id=campaign_id)
            .select_related("contact", "campaign")
            .annotate(derived_status=build_derived_status_expression())
            .order_by("-created_at")
        )

        search = self.request.query_params.get("search", "").strip()
        current_status = self.request.query_params.get("current_status", "").strip()
        derived_status = self.request.query_params.get("derived_status", "").strip()

        if search:
            queryset = queryset.filter(
                Q(destination__icontains=search)
                | Q(contact__phone_number__icontains=search)
            )
        if current_status:
            queryset = queryset.filter(status=current_status)
        if derived_status:
            queryset = queryset.filter(derived_status=derived_status)
        return queryset

    def list(self, request, *args, **kwargs):
        campaign = self.get_campaign()
        queryset = self.filter_queryset(self.get_queryset())
        summary_queryset = (
            CallLog.objects.filter(owner=self.get_profile(), campaign=campaign)
            .annotate(derived_status=build_derived_status_expression())
            .order_by("-created_at")
        )
        classified_total = summary_queryset.exclude(
            derived_status=CALL_STATUS_OTHER
        ).count()
        success_count = summary_queryset.filter(
            derived_status=CALL_STATUS_SUCCESS
        ).count()
        invalid_number_count = summary_queryset.filter(
            derived_status=CALL_STATUS_INVALID_NUMBER
        ).count()
        not_answered_count = summary_queryset.filter(
            derived_status=CALL_STATUS_NOT_ANSWERED
        ).count()

        if classified_total:
            success_rate = round(success_count / classified_total * 100, 2)
            invalid_number_rate = round(
                invalid_number_count / classified_total * 100, 2
            )
            not_answered_rate = round(not_answered_count / classified_total * 100, 2)
        else:
            success_rate = 0.0
            invalid_number_rate = 0.0
            not_answered_rate = 0.0

        summary = serialize_campaign_call_log_summary(
            campaign=campaign,
            filters={
                "search": request.query_params.get("search", "").strip(),
                "current_status": request.query_params.get(
                    "current_status", ""
                ).strip(),
                "derived_status": request.query_params.get(
                    "derived_status", ""
                ).strip(),
            },
            counts={
                "ongoing_calls": campaign.call_logs.filter(
                    status__in=ACTIVE_CALL_STATES
                ).count(),
                "contact_count": campaign.contacts.count(),
                "completed_calls": classified_total,
                "success_calls": success_count,
                "invalid_number_calls": invalid_number_count,
                "not_answered_calls": not_answered_count,
            },
            rates={
                "success_rate": success_rate,
                "invalid_number_rate": invalid_number_rate,
                "not_answered_rate": not_answered_rate,
            },
        )

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        if page is not None:
            paginated = self.get_paginated_response(serializer.data)
            paginated.data["summary"] = summary
            return paginated

        return Response({"results": serializer.data, "summary": summary})


class CampaignRestartView(ExternalSessionMixin, APIView):
    def get_campaign(self, campaign_id: UUID) -> Campaign:
        campaign = Campaign.objects.filter(
            owner=self.get_profile(), pk=campaign_id
        ).first()
        if campaign is None:
            raise ValidationError({"detail": "Campaign not found."})
        return campaign

    def post(self, request, campaign_id: UUID):
        campaign = self.get_campaign(campaign_id)
        serializer = CampaignRestartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        restart_scope = serializer.validated_data["restart_scope"]
        run_mode = serializer.validated_data["run_mode"]
        scheduled_at = serializer.validated_data.get("scheduled_at")
        now = timezone.now()

        latest_logs = (
            campaign.call_logs.filter(contact_id__isnull=False)
            .annotate(derived_status=build_derived_status_expression())
            .order_by("contact_id", "-created_at")
        )
        latest_statuses = collect_latest_contact_statuses(latest_logs)

        selected_contact_ids: list[str] = []
        invalid_contact_ids: list[str] = []
        paused_contact_ids: list[str] = []
        all_contact_ids = list(campaign.contacts.values_list("id", flat=True))

        for contact_id in all_contact_ids:
            derived_status = latest_statuses.get(contact_id, CALL_STATUS_OTHER)
            include_contact = False
            if restart_scope == "all":
                include_contact = True
            elif restart_scope == "not_answered":
                include_contact = derived_status == CALL_STATUS_NOT_ANSWERED
            elif restart_scope == "exclude_invalid":
                include_contact = derived_status != CALL_STATUS_INVALID_NUMBER

            if include_contact:
                selected_contact_ids.append(contact_id)
            elif derived_status == CALL_STATUS_INVALID_NUMBER:
                invalid_contact_ids.append(contact_id)
            else:
                paused_contact_ids.append(contact_id)

        if not selected_contact_ids:
            raise ValidationError(
                {"detail": "No contacts match the selected restart scope."}
            )

        reset_campaign_runtime_state(campaign, reset_contacts=False, now=now)
        campaign.contacts.filter(pk__in=selected_contact_ids).update(
            status=Contact.ContactStatus.NEW,
            updated_at=now,
        )
        if invalid_contact_ids:
            campaign.contacts.filter(pk__in=invalid_contact_ids).update(
                status=Contact.ContactStatus.INVALID,
                updated_at=now,
            )
        if paused_contact_ids:
            campaign.contacts.filter(pk__in=paused_contact_ids).update(
                status=Contact.ContactStatus.PAUSED,
                updated_at=now,
            )

        if run_mode == "scheduled":
            campaign.status = Campaign.CampaignStatus.SCHEDULED
            campaign.scheduled_at = scheduled_at
            campaign.started_at = None
        else:
            campaign.status = Campaign.CampaignStatus.PROCESSING
            campaign.scheduled_at = None
            campaign.started_at = now

        campaign.finished_at = None
        campaign.paused_at = None
        campaign.last_dispatched_at = None
        campaign.save(
            update_fields=[
                "status",
                "scheduled_at",
                "started_at",
                "finished_at",
                "paused_at",
                "last_dispatched_at",
                "updated_at",
            ]
        )

        if run_mode == "immediate":
            dispatch_campaign_calls_task.delay(str(campaign.id))

        return Response(
            {
                "campaign": CampaignSerializer(
                    campaign, context={"request": request}
                ).data,
                "selected_contact_count": len(selected_contact_ids),
            }
        )


class CallStateWebhookView(APIView):
    parser_classes = [JSONParser]  # noqa: RUF012

    def post(self, request):
        append_webhook_payload("call-state.log", request.data)
        call_log = handle_state_webhook(request.data)
        payload = (
            request.data.get("call_info") if isinstance(request.data, dict) else None
        )
        normalized_payload = payload if isinstance(payload, dict) else request.data
        if (
            call_log.status == "connected"
            and call_log.pk
            and isinstance(normalized_payload, dict)
            and is_internal_outgoing_leg(normalized_payload)
            and call_log.playback_requested_at is None
        ):
            play_campaign_audio_task.delay(str(call_log.pk))
        return Response({"success": 1, "call_log_id": call_log.pk})


class PlaybackWebhookView(APIView):
    parser_classes = [JSONParser]  # noqa: RUF012

    def post(self, request):
        append_webhook_payload("playback-events.log", request.data)
        call_log = handle_playback_webhook(request.data)
        return Response(
            {"success": 1, "call_log_id": call_log.pk if call_log else None}
        )
