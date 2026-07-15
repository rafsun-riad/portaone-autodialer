from django.contrib import admin

from .models import CallLog, Campaign, CampaignAudio, Contact, ExternalUserProfile


@admin.register(ExternalUserProfile)
class ExternalUserProfileAdmin(admin.ModelAdmin):
    list_display = ("username", "i_customer", "last_synced_at", "updated_at")
    search_fields = ("username", "i_customer")


class CampaignAudioInline(admin.StackedInline):
    model = CampaignAudio
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "scheduled_at", "campaign_pace")
    list_filter = ("status",)
    search_fields = ("name", "owner__username", "connect_to", "caller_id")
    inlines = [CampaignAudioInline]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "campaign", "status", "owner")
    list_filter = ("status", "campaign")
    search_fields = ("name", "phone_number", "campaign__name", "owner__username")


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = (
        "tracking_id",
        "campaign",
        "contact",
        "status",
        "duration",
        "update_time",
    )
    list_filter = ("status",)
    search_fields = ("tracking_id", "external_call_id", "destination", "caller_id")


# Register your models here.
