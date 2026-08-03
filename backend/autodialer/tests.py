from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from autodialer.models import CallLog, Campaign, Contact, ExternalUserProfile


class CampaignCallLogViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.profile = ExternalUserProfile.objects.create(
            username="operator",
            access_token="token",
        )
        self.campaign = Campaign.objects.create(
            owner=self.profile,
            name="August Campaign",
            status=Campaign.CampaignStatus.FINISHED,
            connect_to="1001",
            billable_account="1001",
            caller_id="8801700000000",
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        self.success_contact = Contact.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            phone_number="8801700000001",
            name="Success Contact",
            status=Contact.ContactStatus.CALLED,
        )
        self.not_answered_contact = Contact.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            phone_number="8801700000002",
            name="Not Answered Contact",
            status=Contact.ContactStatus.FAILED,
        )
        self.invalid_contact = Contact.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            phone_number="8801700000003",
            name="Invalid Contact",
            status=Contact.ContactStatus.INVALID,
        )

        CallLog.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            contact=self.success_contact,
            external_call_id="call-success",
            status="terminated",
            account_id="1001",
            caller_id="8801700000000",
            destination=self.success_contact.phone_number,
            reason="BYE Received",
            reason_code=487,
            duration=32,
            connect_time=timezone.now(),
        )
        CallLog.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            contact=self.not_answered_contact,
            external_call_id="call-no-answer",
            status="terminated",
            account_id="1001",
            caller_id="8801700000000",
            destination=self.not_answered_contact.phone_number,
            reason="Temporarily Unavailable",
            reason_code=480,
            duration=0,
        )
        CallLog.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            contact=self.invalid_contact,
            external_call_id="call-invalid",
            status="terminated",
            account_id="1001",
            caller_id="8801700000000",
            destination=self.invalid_contact.phone_number,
            reason="Auth Failed",
            reason_code=403,
            duration=0,
        )

    def authenticate(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer token",
            HTTP_X_PORTAL_USERNAME=self.profile.username,
        )

    def test_list_returns_summary_and_derived_status(self):
        self.authenticate()

        response = self.client.get(f"/api/campaigns/{self.campaign.id}/calls/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["counts"]["completed_calls"], 3)
        self.assertEqual(response.data["summary"]["counts"]["success_calls"], 1)
        self.assertEqual(response.data["summary"]["counts"]["invalid_number_calls"], 1)
        self.assertEqual(response.data["summary"]["counts"]["not_answered_calls"], 1)
        self.assertEqual(
            response.data["results"][0]["campaign_name"], self.campaign.name
        )
        self.assertIn(
            response.data["results"][0]["derived_status"],
            ["success", "invalid_number", "not_answered"],
        )

    def test_restart_can_schedule_only_not_answered_contacts(self):
        self.authenticate()

        scheduled_at = timezone.now() + timedelta(hours=2)
        response = self.client.post(
            f"/api/campaigns/{self.campaign.id}/restart/",
            {
                "restart_scope": "not_answered",
                "run_mode": "scheduled",
                "scheduled_at": scheduled_at.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_contact_count"], 1)

        self.success_contact.refresh_from_db()
        self.not_answered_contact.refresh_from_db()
        self.invalid_contact.refresh_from_db()
        self.campaign.refresh_from_db()

        self.assertEqual(self.campaign.status, Campaign.CampaignStatus.SCHEDULED)
        self.assertEqual(self.not_answered_contact.status, Contact.ContactStatus.NEW)
        self.assertEqual(self.success_contact.status, Contact.ContactStatus.PAUSED)
        self.assertEqual(self.invalid_contact.status, Contact.ContactStatus.INVALID)
