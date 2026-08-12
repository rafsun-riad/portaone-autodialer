from __future__ import annotations

import csv
import io
from datetime import timedelta
from uuid import UUID

from django.db.models import Count, DateTimeField, Max, Min, Q
from django.db.models.functions import Coalesce, TruncDay, TruncHour
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
    CallLogExportJob,
    Campaign,
    CampaignAudio,
    Contact,
    ContactImportJob,
    ExternalUserProfile,
)
from autodialer.serializers import (
    CallLogExportJobSerializer,
    CallLogSerializer,
    CampaignAudioSerializer,
    CampaignRestartSerializer,
    CampaignSerializer,
    ChangePasswordSerializer,
    ContactImportFailureSerializer,
    ContactImportJobSerializer,
    ContactSerializer,
    LoginSerializer,
    serialize_campaign_call_log_summary,
)
from autodialer.services.call_logs import (
    CALL_STATUS_INVALID_NUMBER,
    CALL_STATUS_NOT_ANSWERED,
    CALL_STATUS_OTHER,
    CALL_STATUS_SUCCESS,
    build_call_log_export_filename,
    build_derived_status_expression,
    collect_latest_contact_statuses,
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
from autodialer.tasks import (
    cleanup_call_log_export_file_task,
    dispatch_campaign_calls_task,
    play_campaign_audio_task,
    process_call_log_export_task,
    process_contact_import_task,
    schedule_call_log_export_file_cleanup,
)


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


class ContactImportFailurePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


ACTIVE_CONTACT_IMPORT_STATUSES = [
    ContactImportJob.Status.PENDING,
    ContactImportJob.Status.PREPARING,
    ContactImportJob.Status.PROCESSING,
]
ACTIVE_CALL_LOG_EXPORT_STATUSES = [
    CallLogExportJob.Status.PENDING,
    CallLogExportJob.Status.PREPARING,
    CallLogExportJob.Status.PROCESSING,
]


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

        active_job = (
            ContactImportJob.objects.filter(
                owner=profile,
                campaign=campaign,
                status__in=ACTIVE_CONTACT_IMPORT_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
        if active_job is not None:
            return Response(
                {
                    "detail": "A contact import is already running for this campaign.",
                    "job": ContactImportJobSerializer(active_job).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            sample = upload.read(8192).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                {"detail": "CSV file must be UTF-8 encoded."}
            ) from exc
        finally:
            upload.seek(0)

        reader = csv.DictReader(io.StringIO(sample))
        if reader.fieldnames is None or "phone_number" not in reader.fieldnames:
            raise ValidationError(
                {"detail": "CSV must include a 'phone_number' column."}
            )

        job = ContactImportJob.objects.create(
            owner=profile,
            campaign=campaign,
            csv_file=upload,
            original_filename=upload.name,
        )
        process_contact_import_task.delay(str(job.id))
        return Response(
            ContactImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED
        )


class ContactImportJobDetailView(ExternalSessionMixin, APIView):
    def get(self, request, job_id: UUID):
        job = (
            ContactImportJob.objects.select_related("campaign")
            .filter(owner=self.get_profile(), pk=job_id)
            .first()
        )
        if job is None:
            raise ValidationError({"detail": "Import job not found."})
        return Response(ContactImportJobSerializer(job).data)


class ActiveContactImportJobView(ExternalSessionMixin, APIView):
    def get(self, request):
        campaign_id = request.query_params.get("campaign", "").strip()
        if not campaign_id:
            raise ValidationError({"campaign": "Campaign is required."})

        job = (
            ContactImportJob.objects.select_related("campaign")
            .filter(
                owner=self.get_profile(),
                campaign_id=campaign_id,
                status__in=ACTIVE_CONTACT_IMPORT_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
        return Response(
            {
                "job": ContactImportJobSerializer(job).data if job else None,
            }
        )


class ContactImportFailureListView(ExternalSessionMixin, APIView):
    pagination_class = ContactImportFailurePagination

    def get(self, request, job_id: UUID):
        job = ContactImportJob.objects.filter(
            owner=self.get_profile(), pk=job_id
        ).first()
        if job is None:
            raise ValidationError({"detail": "Import job not found."})

        queryset = job.failures.order_by("row_number", "created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = ContactImportFailureSerializer(page or queryset, many=True)
        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response({"results": serializer.data})


class CancelContactImportJobView(ExternalSessionMixin, APIView):
    def post(self, request, job_id: UUID):
        job = ContactImportJob.objects.filter(
            owner=self.get_profile(), pk=job_id
        ).first()
        if job is None:
            raise ValidationError({"detail": "Import job not found."})
        if job.status in [
            ContactImportJob.Status.COMPLETED,
            ContactImportJob.Status.FAILED,
            ContactImportJob.Status.CANCELED,
        ]:
            raise ValidationError(
                {"detail": f"Cannot cancel a job in '{job.status}' status."}
            )

        job.cancel_requested = True
        job.save(update_fields=["cancel_requested", "updated_at"])
        return Response(
            ContactImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED
        )


class CampaignCallLogExportView(ExternalSessionMixin, APIView):
    def get_campaign(self, campaign_id: UUID) -> Campaign:
        campaign = Campaign.objects.filter(
            owner=self.get_profile(), pk=campaign_id
        ).first()
        if campaign is None:
            raise ValidationError({"detail": "Campaign not found."})
        return campaign

    def get(self, request, campaign_id: UUID):
        campaign = self.get_campaign(campaign_id)
        profile = self.get_profile()
        now = timezone.now()

        job = (
            CallLogExportJob.objects.select_related("campaign")
            .filter(
                owner=profile,
                campaign=campaign,
                status__in=ACTIVE_CALL_LOG_EXPORT_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
        if job is None:
            job = (
                CallLogExportJob.objects.select_related("campaign")
                .filter(
                    owner=profile,
                    campaign=campaign,
                    status=CallLogExportJob.Status.COMPLETED,
                    expires_at__isnull=False,
                    expires_at__gt=now,
                )
                .exclude(export_file="")
                .order_by("-created_at")
                .first()
            )

        return Response({"job": CallLogExportJobSerializer(job).data if job else None})

    def post(self, request, campaign_id: UUID):
        campaign = self.get_campaign(campaign_id)
        profile = self.get_profile()

        if campaign.status not in [
            Campaign.CampaignStatus.PAUSED,
            Campaign.CampaignStatus.FINISHED,
        ]:
            raise ValidationError(
                {"detail": "Pause or finish the campaign before exporting call logs."}
            )

        active_job = (
            CallLogExportJob.objects.select_related("campaign")
            .filter(
                owner=profile,
                campaign=campaign,
                status__in=ACTIVE_CALL_LOG_EXPORT_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
        if active_job is not None:
            return Response(
                {
                    "detail": "A call log export is already running for this campaign.",
                    "job": CallLogExportJobSerializer(active_job).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        job = CallLogExportJob.objects.create(
            owner=profile,
            campaign=campaign,
            original_filename=build_call_log_export_filename(campaign, timezone.now()),
        )
        process_call_log_export_task.delay(str(job.id))
        return Response(
            CallLogExportJobSerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )


class CallLogExportJobDetailView(ExternalSessionMixin, APIView):
    def get(self, request, job_id: UUID):
        job = (
            CallLogExportJob.objects.select_related("campaign")
            .filter(owner=self.get_profile(), pk=job_id)
            .first()
        )
        if job is None:
            raise ValidationError({"detail": "Export job not found."})
        return Response(CallLogExportJobSerializer(job).data)


class CancelCallLogExportJobView(ExternalSessionMixin, APIView):
    def post(self, request, job_id: UUID):
        job = CallLogExportJob.objects.filter(
            owner=self.get_profile(), pk=job_id
        ).first()
        if job is None:
            raise ValidationError({"detail": "Export job not found."})
        if job.status in [
            CallLogExportJob.Status.COMPLETED,
            CallLogExportJob.Status.FAILED,
            CallLogExportJob.Status.CANCELED,
        ]:
            raise ValidationError(
                {"detail": f"Cannot cancel a job in '{job.status}' status."}
            )

        job.cancel_requested = True
        job.save(update_fields=["cancel_requested", "updated_at"])
        return Response(
            CallLogExportJobSerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DownloadCallLogExportJobView(ExternalSessionMixin, APIView):
    def get(self, request, job_id: UUID):
        job = (
            CallLogExportJob.objects.select_related("campaign")
            .filter(owner=self.get_profile(), pk=job_id)
            .first()
        )
        if job is None:
            raise ValidationError({"detail": "Export job not found."})
        if job.status != CallLogExportJob.Status.COMPLETED or not job.export_file:
            raise ValidationError({"detail": "Export file is not ready yet."})

        now = timezone.now()
        if job.expires_at is not None and job.expires_at <= now:
            cleanup_call_log_export_file_task(str(job.id))
            raise Http404("Export file expired.")

        if job.first_downloaded_at is None:
            job.first_downloaded_at = now
            job.expires_at = now + timedelta(hours=1)
            job.save(update_fields=["first_downloaded_at", "expires_at", "updated_at"])
            schedule_call_log_export_file_cleanup(str(job.id), 3600)

        job.export_file.open("rb")
        response = FileResponse(job.export_file, content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{job.original_filename or "call-logs.csv"}"'
        )
        return response


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


class CampaignCallLogAnalyticsView(ExternalSessionMixin, APIView):
    def get_campaign(self, campaign_id: UUID) -> Campaign:
        campaign = Campaign.objects.filter(
            owner=self.get_profile(), pk=campaign_id
        ).first()
        if campaign is None:
            raise ValidationError({"detail": "Campaign not found."})
        return campaign

    def get_queryset(self, campaign: Campaign):
        return CallLog.objects.filter(
            owner=self.get_profile(), campaign=campaign
        ).annotate(
            derived_status=build_derived_status_expression(),
            call_time=Coalesce(
                "connect_time",
                "start_time",
                "created_at",
                output_field=DateTimeField(),
            ),
        )

    def get(self, request, campaign_id: UUID):
        campaign = self.get_campaign(campaign_id)
        queryset = self.get_queryset(campaign)

        current_status = request.query_params.get("current_status", "").strip()
        derived_status = request.query_params.get("derived_status", "").strip()
        bucket = request.query_params.get("bucket", "auto").strip() or "auto"

        if current_status:
            queryset = queryset.filter(status=current_status)
        if derived_status:
            queryset = queryset.filter(derived_status=derived_status)
        if bucket not in {"auto", "hour", "day"}:
            raise ValidationError(
                {"bucket": "Bucket must be one of auto, hour, or day."}
            )

        if bucket == "auto":
            bounds = queryset.aggregate(
                first_call=Min("call_time"), last_call=Max("call_time")
            )
            first_call = bounds["first_call"]
            last_call = bounds["last_call"]
            if (
                first_call is not None
                and last_call is not None
                and last_call - first_call >= timedelta(days=3)
            ):
                bucket = "day"
            else:
                bucket = "hour"

        bucket_expression = (
            TruncDay("call_time") if bucket == "day" else TruncHour("call_time")
        )
        timeline_queryset = (
            queryset.exclude(call_time__isnull=True)
            .annotate(bucket=bucket_expression)
            .values("bucket")
            .annotate(
                success=Count("id", filter=Q(derived_status=CALL_STATUS_SUCCESS)),
                invalid_number=Count(
                    "id", filter=Q(derived_status=CALL_STATUS_INVALID_NUMBER)
                ),
                not_answered=Count(
                    "id", filter=Q(derived_status=CALL_STATUS_NOT_ANSWERED)
                ),
                ongoing=Count("id", filter=Q(status__in=ACTIVE_CALL_STATES)),
            )
            .order_by("bucket")
        )

        classified_total = queryset.exclude(derived_status=CALL_STATUS_OTHER).count()
        success_count = queryset.filter(derived_status=CALL_STATUS_SUCCESS).count()
        invalid_number_count = queryset.filter(
            derived_status=CALL_STATUS_INVALID_NUMBER
        ).count()
        not_answered_count = queryset.filter(
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

        return Response(
            {
                "campaign": {
                    "id": str(campaign.id),
                    "name": campaign.name,
                    "status": campaign.status,
                    "started_at": campaign.started_at,
                    "finished_at": campaign.finished_at,
                },
                "filters": {
                    "current_status": current_status,
                    "derived_status": derived_status,
                    "bucket": bucket,
                },
                "summary": {
                    "counts": {
                        "total_calls": queryset.count(),
                        "ongoing_calls": queryset.filter(
                            status__in=ACTIVE_CALL_STATES
                        ).count(),
                        "classified_calls": classified_total,
                        "success_calls": success_count,
                        "invalid_number_calls": invalid_number_count,
                        "not_answered_calls": not_answered_count,
                    },
                    "rates": {
                        "success_rate": success_rate,
                        "invalid_number_rate": invalid_number_rate,
                        "not_answered_rate": not_answered_rate,
                    },
                },
                "timeline": [
                    {
                        "bucket": item["bucket"],
                        "success": item["success"],
                        "invalid_number": item["invalid_number"],
                        "not_answered": item["not_answered"],
                        "ongoing": item["ongoing"],
                    }
                    for item in timeline_queryset
                ],
            }
        )


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
