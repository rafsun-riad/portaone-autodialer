import os
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from autodialer.models import (
    CallLog,
    CallLogExportJob,
    Campaign,
    Contact,
    ContactImportFailure,
    ContactImportJob,
    ExternalUserProfile,
)
from autodialer.tasks import (
    cleanup_contact_import_csv_file_task,
    cleanup_stale_call_log_export_files,
    cleanup_stale_contact_import_csv_files,
    process_call_log_export_task,
    process_contact_import_task,
)


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
        CallLog.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            contact=self.success_contact,
            external_call_id="call-ongoing",
            status="ringing",
            account_id="1001",
            caller_id="8801700000000",
            destination="8801700000004",
            reason="",
            reason_code=None,
            duration=0,
            start_time=timezone.now() + timedelta(minutes=5),
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
        self.assertTrue(
            {item["derived_status"] for item in response.data["results"]}.issuperset(
                {"success", "invalid_number", "not_answered", "other"}
            )
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

    def test_analytics_returns_timeline_and_summary(self):
        self.authenticate()

        response = self.client.get(
            f"/api/campaigns/{self.campaign.id}/calls/analytics/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["counts"]["total_calls"], 4)
        self.assertEqual(response.data["summary"]["counts"]["ongoing_calls"], 1)
        self.assertEqual(response.data["summary"]["counts"]["success_calls"], 1)
        self.assertEqual(response.data["summary"]["counts"]["invalid_number_calls"], 1)
        self.assertEqual(response.data["summary"]["counts"]["not_answered_calls"], 1)
        self.assertEqual(response.data["summary"]["rates"]["success_rate"], 33.33)
        self.assertEqual(len(response.data["timeline"]), 1)
        self.assertEqual(response.data["timeline"][0]["success"], 1)
        self.assertEqual(response.data["timeline"][0]["invalid_number"], 1)
        self.assertEqual(response.data["timeline"][0]["not_answered"], 1)
        self.assertEqual(response.data["timeline"][0]["ongoing"], 1)

    def test_analytics_respects_filters_and_start_time_fallback(self):
        self.authenticate()

        response = self.client.get(
            f"/api/campaigns/{self.campaign.id}/calls/analytics/?current_status=ringing"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["counts"]["total_calls"], 1)
        self.assertEqual(response.data["summary"]["counts"]["ongoing_calls"], 1)
        self.assertEqual(response.data["summary"]["counts"]["classified_calls"], 0)
        self.assertEqual(len(response.data["timeline"]), 1)
        self.assertEqual(response.data["timeline"][0]["ongoing"], 1)
        self.assertEqual(response.data["timeline"][0]["success"], 0)


class ContactImportJobTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.client = APIClient()
        self.profile = ExternalUserProfile.objects.create(
            username="operator",
            access_token="token",
        )
        self.campaign = Campaign.objects.create(
            owner=self.profile,
            name="Import Campaign",
            status=Campaign.CampaignStatus.NEW,
            connect_to="1001",
            billable_account="1001",
            caller_id="8801700000000",
        )

    def authenticate(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer token",
            HTTP_X_PORTAL_USERNAME=self.profile.username,
        )

    @patch("autodialer.views.process_contact_import_task.delay")
    def test_bulk_upload_creates_async_import_job(self, delay_mock):
        self.authenticate()

        csv_file = SimpleUploadedFile(
            "contacts.csv",
            b"phone_number,name,comments,status\n01700000001,Alpha,,new\n",
            content_type="text/csv",
        )

        response = self.client.post(
            "/api/contacts/bulk-upload/",
            {"campaign": str(self.campaign.id), "file": csv_file},
        )

        self.assertEqual(response.status_code, 202)
        job = ContactImportJob.objects.get(pk=response.data["id"])
        self.assertEqual(job.owner, self.profile)
        self.assertEqual(job.campaign, self.campaign)
        self.assertEqual(job.status, ContactImportJob.Status.PENDING)
        self.assertEqual(job.original_filename, "contacts.csv")
        self.assertTrue(job.csv_file.name.endswith("contacts.csv"))
        delay_mock.assert_called_once_with(str(job.id))

    def test_active_job_and_cancel_endpoints(self):
        self.authenticate()
        job = ContactImportJob.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            status=ContactImportJob.Status.PROCESSING,
            original_filename="contacts.csv",
            csv_file=SimpleUploadedFile(
                "contacts.csv",
                b"phone_number,name\n01700000001,Alpha\n",
                content_type="text/csv",
            ),
        )

        active_response = self.client.get(
            f"/api/contacts/import-jobs/active/?campaign={self.campaign.id}"
        )
        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(active_response.data["job"]["id"], str(job.id))

        cancel_response = self.client.post(
            f"/api/contacts/import-jobs/{job.id}/cancel/"
        )
        self.assertEqual(cancel_response.status_code, 202)
        job.refresh_from_db()
        self.assertTrue(job.cancel_requested)

    @patch("autodialer.tasks.cleanup_contact_import_csv_file_task.apply_async")
    def test_process_contact_import_task_persists_failures_and_duplicates(
        self, cleanup_mock
    ):
        existing_contact = Contact.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            phone_number="8801700000002",
            name="Existing",
            status=Contact.ContactStatus.NEW,
        )
        self.assertEqual(existing_contact.phone_number, "8801700000002")

        csv_file = SimpleUploadedFile(
            "contacts.csv",
            (
                b"phone_number,name,comments,status\n"
                b"01700000001,Alpha,,new\n"
                b"01700000002,Already There,,new\n"
                b"bad-number,Invalid,,new\n"
                b"01700000003,Bravo,,new\n"
                b"01700000003,Bravo Duplicate,,new\n"
            ),
            content_type="text/csv",
        )
        job = ContactImportJob.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            original_filename="contacts.csv",
            csv_file=csv_file,
        )

        result = process_contact_import_task(str(job.id))

        job.refresh_from_db()
        self.assertEqual(result["status"], ContactImportJob.Status.COMPLETED)
        self.assertEqual(job.status, ContactImportJob.Status.COMPLETED)
        self.assertEqual(job.total_rows, 5)
        self.assertEqual(job.processed_rows, 5)
        self.assertEqual(job.created_count, 2)
        self.assertEqual(job.failed_count, 3)
        self.assertEqual(self.campaign.contacts.count(), 3)
        cleanup_mock.assert_called_once_with(args=[str(job.id)], countdown=300)

        failures = list(
            ContactImportFailure.objects.filter(job=job).order_by("row_number")
        )
        self.assertEqual([failure.row_number for failure in failures], [3, 4, 6])
        self.assertIn("Duplicate phone number", failures[0].failure_reason)
        self.assertIn("phone_number", failures[1].failure_reason)
        self.assertIn("Duplicate phone number", failures[2].failure_reason)

        failure_response = self.client.get(
            f"/api/contacts/import-jobs/{job.id}/failures/?page=1&page_size=2",
            HTTP_AUTHORIZATION="Bearer token",
            HTTP_X_PORTAL_USERNAME=self.profile.username,
        )
        self.assertEqual(failure_response.status_code, 200)
        self.assertEqual(failure_response.data["count"], 3)
        self.assertEqual(len(failure_response.data["results"]), 2)

    @patch("autodialer.tasks.cleanup_contact_import_csv_file_task.apply_async")
    def test_process_contact_import_task_honors_cancel_before_processing(
        self, cleanup_mock
    ):
        job = ContactImportJob.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            status=ContactImportJob.Status.PENDING,
            cancel_requested=True,
            original_filename="contacts.csv",
            csv_file=SimpleUploadedFile(
                "contacts.csv",
                b"phone_number,name\n01700000001,Alpha\n",
                content_type="text/csv",
            ),
        )

        result = process_contact_import_task(str(job.id))

        job.refresh_from_db()
        self.assertEqual(result["status"], ContactImportJob.Status.CANCELED)
        self.assertEqual(job.status, ContactImportJob.Status.CANCELED)
        self.assertEqual(job.processed_rows, 0)
        self.assertEqual(self.campaign.contacts.count(), 0)
        cleanup_mock.assert_called_once_with(args=[str(job.id)], countdown=300)

    def test_cleanup_contact_import_csv_file_task_deletes_stored_csv(self):
        job = ContactImportJob.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            status=ContactImportJob.Status.COMPLETED,
            original_filename="contacts.csv",
            csv_file=SimpleUploadedFile(
                "contacts.csv",
                b"phone_number,name\n01700000001,Alpha\n",
                content_type="text/csv",
            ),
        )

        file_path = job.csv_file.path
        self.assertTrue(job.csv_file.storage.exists(job.csv_file.name))

        result = cleanup_contact_import_csv_file_task(str(job.id))

        job.refresh_from_db()
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(job.csv_file.name, "")
        self.assertFalse(os.path.exists(file_path))

    def test_cleanup_stale_contact_import_csv_files_deletes_only_overdue_files(self):
        old_job = ContactImportJob.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            status=ContactImportJob.Status.COMPLETED,
            original_filename="old.csv",
            completed_at=timezone.now() - timedelta(minutes=10),
            csv_file=SimpleUploadedFile(
                "old.csv",
                b"phone_number,name\n01700000001,Alpha\n",
                content_type="text/csv",
            ),
        )
        recent_job = ContactImportJob.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            status=ContactImportJob.Status.COMPLETED,
            original_filename="recent.csv",
            completed_at=timezone.now() - timedelta(minutes=1),
            csv_file=SimpleUploadedFile(
                "recent.csv",
                b"phone_number,name\n01700000002,Bravo\n",
                content_type="text/csv",
            ),
        )
        active_job = ContactImportJob.objects.create(
            owner=self.profile,
            campaign=self.campaign,
            status=ContactImportJob.Status.PROCESSING,
            original_filename="active.csv",
            csv_file=SimpleUploadedFile(
                "active.csv",
                b"phone_number,name\n01700000003,Charlie\n",
                content_type="text/csv",
            ),
        )

        old_path = old_job.csv_file.path
        recent_path = recent_job.csv_file.path
        active_path = active_job.csv_file.path

        deleted_count = cleanup_stale_contact_import_csv_files()

        old_job.refresh_from_db()
        recent_job.refresh_from_db()
        active_job.refresh_from_db()
        self.assertEqual(deleted_count, 1)
        self.assertEqual(old_job.csv_file.name, "")
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(recent_job.csv_file.name)
        self.assertTrue(os.path.exists(recent_path))
        self.assertTrue(active_job.csv_file.name)
        self.assertTrue(os.path.exists(active_path))


class CallLogExportJobTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.client = APIClient()
        self.profile = ExternalUserProfile.objects.create(
            username="export-operator",
            access_token="token",
        )
        self.paused_campaign = Campaign.objects.create(
            owner=self.profile,
            name="Paused Export Campaign",
            status=Campaign.CampaignStatus.PAUSED,
            connect_to="1001",
            billable_account="1001",
            caller_id="8801700000000",
            started_at=timezone.now(),
        )
        self.processing_campaign = Campaign.objects.create(
            owner=self.profile,
            name="Processing Campaign",
            status=Campaign.CampaignStatus.PROCESSING,
            connect_to="1002",
            billable_account="1002",
            caller_id="8801700000000",
            started_at=timezone.now(),
        )
        self.contact = Contact.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            phone_number="8801700000001",
            name="Export Contact",
            status=Contact.ContactStatus.CALLED,
        )
        CallLog.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            contact=self.contact,
            external_call_id="call-success",
            status="terminated",
            account_id="1001",
            caller_id="8801700000000",
            destination=self.contact.phone_number,
            reason="BYE Received",
            reason_code=487,
            duration=32,
            connect_time=timezone.now(),
            playback_requested_at=timezone.now(),
            playback_completed_at=timezone.now(),
        )
        CallLog.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            contact=self.contact,
            external_call_id="call-invalid",
            status="failed",
            account_id="1001",
            caller_id="8801700000000",
            destination="8801700000002",
            reason="Auth Failed",
            reason_code=403,
            duration=0,
        )

    def authenticate(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer token",
            HTTP_X_PORTAL_USERNAME=self.profile.username,
        )

    @patch("autodialer.views.process_call_log_export_task.delay")
    def test_start_export_creates_async_job_for_paused_campaign(self, delay_mock):
        self.authenticate()

        response = self.client.post(
            f"/api/campaigns/{self.paused_campaign.id}/calls/export/"
        )

        self.assertEqual(response.status_code, 202)
        job = CallLogExportJob.objects.get(pk=response.data["id"])
        self.assertEqual(job.owner, self.profile)
        self.assertEqual(job.campaign, self.paused_campaign)
        self.assertEqual(job.status, CallLogExportJob.Status.PENDING)
        self.assertTrue(job.original_filename.endswith(".csv"))
        delay_mock.assert_called_once_with(str(job.id))

    @patch("autodialer.views.process_call_log_export_task.delay")
    def test_start_export_rejects_ineligible_campaign_status(self, delay_mock):
        self.authenticate()

        response = self.client.post(
            f"/api/campaigns/{self.processing_campaign.id}/calls/export/"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Pause or finish the campaign", response.data["detail"])
        delay_mock.assert_not_called()

    def test_current_export_endpoint_returns_completed_unexpired_job(self):
        self.authenticate()
        job = CallLogExportJob.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            status=CallLogExportJob.Status.COMPLETED,
            original_filename="paused-export.csv",
            export_file=SimpleUploadedFile(
                "paused-export.csv",
                b"header\nvalue\n",
                content_type="text/csv",
            ),
            total_rows=2,
            processed_rows=2,
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        response = self.client.get(
            f"/api/campaigns/{self.paused_campaign.id}/calls/export/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["job"]["id"], str(job.id))

    @patch("autodialer.tasks.cleanup_call_log_export_file_task.apply_async")
    def test_process_call_log_export_task_generates_csv_file(self, cleanup_mock):
        job = CallLogExportJob.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            original_filename="paused-export.csv",
        )

        result = process_call_log_export_task(str(job.id))

        job.refresh_from_db()
        self.assertEqual(result["status"], CallLogExportJob.Status.COMPLETED)
        self.assertEqual(job.status, CallLogExportJob.Status.COMPLETED)
        self.assertEqual(job.total_rows, 2)
        self.assertEqual(job.processed_rows, 2)
        self.assertTrue(job.export_file.name.endswith("paused-export.csv"))
        cleanup_mock.assert_called_once_with(args=[str(job.id)], countdown=3600)

        with job.export_file.open("rb") as exported_file:
            csv_text = exported_file.read().decode("utf-8")

        self.assertIn(
            "Campaign Name,Campaign Start Time,Campaign Finish Time", csv_text
        )
        self.assertIn("Paused Export Campaign", csv_text)
        self.assertIn("call-success", csv_text)
        self.assertIn("Current status: Terminated", csv_text)
        self.assertIn("Success", csv_text)
        self.assertIn("Invalid Number", csv_text)

    @patch("autodialer.views.schedule_call_log_export_file_cleanup")
    def test_download_updates_first_downloaded_retention(self, cleanup_schedule_mock):
        self.authenticate()
        job = CallLogExportJob.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            status=CallLogExportJob.Status.COMPLETED,
            original_filename="paused-export.csv",
            export_file=SimpleUploadedFile(
                "paused-export.csv",
                b"a,b\n1,2\n",
                content_type="text/csv",
            ),
            total_rows=1,
            processed_rows=1,
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.get(f"/api/call-log-export-jobs/{job.id}/download/")
        downloaded_content = b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(downloaded_content, b"a,b\n1,2\n")
        self.assertIn("paused-export.csv", response["Content-Disposition"])

        job.refresh_from_db()
        self.assertIsNotNone(job.first_downloaded_at)
        self.assertGreater(job.expires_at, timezone.now() + timedelta(minutes=50))
        cleanup_schedule_mock.assert_called_once_with(str(job.id), 3600)

    def test_cleanup_stale_call_log_export_files_deletes_only_expired_files(self):
        expired_job = CallLogExportJob.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            status=CallLogExportJob.Status.COMPLETED,
            original_filename="expired.csv",
            export_file=SimpleUploadedFile(
                "expired.csv",
                b"a,b\n1,2\n",
                content_type="text/csv",
            ),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        fresh_job = CallLogExportJob.objects.create(
            owner=self.profile,
            campaign=self.paused_campaign,
            status=CallLogExportJob.Status.COMPLETED,
            original_filename="fresh.csv",
            export_file=SimpleUploadedFile(
                "fresh.csv",
                b"a,b\n3,4\n",
                content_type="text/csv",
            ),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        expired_path = expired_job.export_file.path
        fresh_path = fresh_job.export_file.path

        deleted_count = cleanup_stale_call_log_export_files()

        expired_job.refresh_from_db()
        fresh_job.refresh_from_db()
        self.assertEqual(deleted_count, 1)
        self.assertEqual(expired_job.export_file.name, "")
        self.assertFalse(os.path.exists(expired_path))
        self.assertTrue(fresh_job.export_file.name)
        self.assertTrue(os.path.exists(fresh_path))
