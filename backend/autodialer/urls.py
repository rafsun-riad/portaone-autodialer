from django.urls import include, path
from rest_framework.routers import DefaultRouter

from autodialer.views import (
    AccountOptionsView,
    ActiveContactImportJobView,
    BulkContactUploadView,
    CallLogExportJobDetailView,
    CallStateWebhookView,
    CampaignActionView,
    CampaignAudioView,
    CampaignCallLogExportView,
    CampaignCallLogView,
    CampaignRestartView,
    CampaignViewSet,
    CancelCallLogExportJobView,
    CancelContactImportJobView,
    ChangePasswordView,
    ContactImportFailureListView,
    ContactImportJobDetailView,
    ContactViewSet,
    DownloadCallLogExportJobView,
    LoginView,
    MeView,
    PlaybackWebhookView,
    PublicCampaignAudioPlaybackView,
)

router = DefaultRouter()
router.register("campaigns", CampaignViewSet, basename="campaign")
router.register("contacts", ContactViewSet, basename="contact")

campaign_call_logs = CampaignCallLogView.as_view({"get": "list"})

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path(
        "auth/change-password/",
        ChangePasswordView.as_view(),
        name="auth-change-password",
    ),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("accounts/options/", AccountOptionsView.as_view(), name="account-options"),
    path(
        "contacts/bulk-upload/",
        BulkContactUploadView.as_view(),
        name="contacts-bulk-upload",
    ),
    path(
        "contacts/import-jobs/active/",
        ActiveContactImportJobView.as_view(),
        name="contact-import-job-active",
    ),
    path(
        "contacts/import-jobs/<uuid:job_id>/",
        ContactImportJobDetailView.as_view(),
        name="contact-import-job-detail",
    ),
    path(
        "contacts/import-jobs/<uuid:job_id>/failures/",
        ContactImportFailureListView.as_view(),
        name="contact-import-job-failures",
    ),
    path(
        "contacts/import-jobs/<uuid:job_id>/cancel/",
        CancelContactImportJobView.as_view(),
        name="contact-import-job-cancel",
    ),
    path(
        "campaigns/<uuid:campaign_id>/audio/",
        CampaignAudioView.as_view(),
        name="campaign-audio",
    ),
    path(
        "campaigns/<uuid:campaign_id>/actions/<str:action_name>/",
        CampaignActionView.as_view(),
        name="campaign-action",
    ),
    path(
        "campaigns/<uuid:campaign_id>/calls/", campaign_call_logs, name="campaign-calls"
    ),
    path(
        "campaigns/<uuid:campaign_id>/calls/export/",
        CampaignCallLogExportView.as_view(),
        name="campaign-call-log-export",
    ),
    path(
        "campaigns/<uuid:campaign_id>/restart/",
        CampaignRestartView.as_view(),
        name="campaign-restart",
    ),
    path(
        "call-log-export-jobs/<uuid:job_id>/",
        CallLogExportJobDetailView.as_view(),
        name="call-log-export-job-detail",
    ),
    path(
        "call-log-export-jobs/<uuid:job_id>/cancel/",
        CancelCallLogExportJobView.as_view(),
        name="call-log-export-job-cancel",
    ),
    path(
        "call-log-export-jobs/<uuid:job_id>/download/",
        DownloadCallLogExportJobView.as_view(),
        name="call-log-export-job-download",
    ),
    path(
        "webhooks/calls/state/",
        CallStateWebhookView.as_view(),
        name="call-state-webhook",
    ),
    path(
        "webhooks/calls/playback/",
        PlaybackWebhookView.as_view(),
        name="playback-webhook",
    ),
    path(
        "public/campaign-audio/<uuid:campaign_id>/<str:versioned_name>",
        PublicCampaignAudioPlaybackView.as_view(),
        name="public-campaign-audio",
    ),
    path("", include(router.urls)),
]
