from django.urls import include, path
from rest_framework.routers import DefaultRouter

from autodialer.views import (
    AccountOptionsView,
    BulkContactUploadView,
    CallStateWebhookView,
    CampaignActionView,
    CampaignAudioView,
    CampaignCallLogView,
    CampaignViewSet,
    ChangePasswordView,
    ContactViewSet,
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
        "campaigns/<int:campaign_id>/audio/",
        CampaignAudioView.as_view(),
        name="campaign-audio",
    ),
    path(
        "campaigns/<int:campaign_id>/actions/<str:action_name>/",
        CampaignActionView.as_view(),
        name="campaign-action",
    ),
    path(
        "campaigns/<int:campaign_id>/calls/", campaign_call_logs, name="campaign-calls"
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
        "public/campaign-audio/<int:campaign_id>/<str:versioned_name>",
        PublicCampaignAudioPlaybackView.as_view(),
        name="public-campaign-audio",
    ),
    path("", include(router.urls)),
]
