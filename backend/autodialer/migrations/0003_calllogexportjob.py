import uuid

import django.db.models.deletion
from django.db import migrations, models

import autodialer.models


class Migration(migrations.Migration):
    dependencies = [
        ("autodialer", "0002_contactimportjob_contactimportfailure_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CallLogExportJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("preparing", "Preparing"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("canceled", "Canceled"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "export_file",
                    models.FileField(
                        blank=True,
                        max_length=255,
                        upload_to=autodialer.models.call_log_export_upload_to,
                    ),
                ),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("processed_rows", models.PositiveIntegerField(default=0)),
                ("cancel_requested", models.BooleanField(default=False)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("first_downloaded_at", models.DateTimeField(blank=True, null=True)),
                (
                    "expires_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("error_message", models.TextField(blank=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="call_log_export_jobs",
                        to="autodialer.campaign",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="call_log_export_jobs",
                        to="autodialer.externaluserprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["owner", "status"],
                        name="autodialer__owner_i_c8d38e_idx",
                    ),
                    models.Index(
                        fields=["owner", "campaign", "status"],
                        name="autodialer__owner_i_1eb81d_idx",
                    ),
                    models.Index(
                        fields=["owner", "expires_at"],
                        name="autodialer__owner_i_9f257f_idx",
                    ),
                ],
            },
        ),
    ]
