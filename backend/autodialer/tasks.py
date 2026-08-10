from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from io import TextIOWrapper
from typing import Any

from celery import shared_task
from django.core.files.base import File
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from autodialer.models import (
    CallLog,
    CallLogExportJob,
    Campaign,
    Contact,
    ContactImportFailure,
    ContactImportJob,
)
from autodialer.serializers import ContactImportRowSerializer
from autodialer.services.call_logs import (
    CALL_LOG_EXPORT_HEADERS,
    build_call_log_export_filename,
    build_call_log_export_row,
    build_derived_status_expression,
)
from autodialer.services.workflows import (
    dispatch_campaign_calls,
    maybe_finish_campaign,
    play_campaign_audio,
)

CONTACT_IMPORT_BATCH_SIZE = 1000
CONTACT_IMPORT_CLEANUP_DELAY_SECONDS = 300
CONTACT_IMPORT_TERMINAL_STATUSES = [
    ContactImportJob.Status.COMPLETED,
    ContactImportJob.Status.FAILED,
    ContactImportJob.Status.CANCELED,
]
CONTACT_IMPORT_DUPLICATE_REASON = (
    "Duplicate phone number already exists in this campaign."
)
CALL_LOG_EXPORT_BATCH_SIZE = 5000
CALL_LOG_EXPORT_RETENTION_SECONDS = 3600
CALL_LOG_EXPORT_TERMINAL_STATUSES = [
    CallLogExportJob.Status.COMPLETED,
    CallLogExportJob.Status.FAILED,
    CallLogExportJob.Status.CANCELED,
]


@dataclass(slots=True)
class PreparedContactRow:
    row_number: int
    phone_number: str
    name: str
    comments: str
    status: str
    row_data: dict[str, Any]


def _serialize_import_errors(error_data: Any) -> str:
    if isinstance(error_data, Mapping):
        messages = []
        for key, value in error_data.items():
            nested_message = _serialize_import_errors(value)
            if nested_message:
                messages.append(f"{key}: {nested_message}")
        return "; ".join(messages)
    if isinstance(error_data, list):
        return "; ".join(
            message
            for message in (_serialize_import_errors(item) for item in error_data)
            if message
        )
    return str(error_data).strip()


def _normalize_import_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized_row: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        cleaned_key = str(key).strip()
        if not cleaned_key:
            continue
        if isinstance(value, str):
            normalized_row[cleaned_key] = value.strip()
        else:
            normalized_row[cleaned_key] = value
    return normalized_row


def _build_import_failure(
    *,
    job: ContactImportJob,
    row_number: int,
    phone_number: str,
    row_data: dict[str, Any],
    reason: str,
) -> ContactImportFailure:
    return ContactImportFailure(
        job=job,
        row_number=row_number,
        phone_number=phone_number,
        row_data=row_data,
        failure_reason=reason,
    )


def _refresh_job(job: ContactImportJob) -> ContactImportJob:
    job.refresh_from_db(
        fields=[
            "status",
            "cancel_requested",
            "processed_rows",
            "created_count",
            "failed_count",
            "total_rows",
        ]
    )
    return job


def _refresh_call_log_export_job(job: CallLogExportJob) -> CallLogExportJob:
    job.refresh_from_db(
        fields=[
            "status",
            "cancel_requested",
            "processed_rows",
            "total_rows",
            "expires_at",
            "first_downloaded_at",
        ]
    )
    return job


def _schedule_contact_import_file_cleanup(job_id: str) -> None:
    cleanup_contact_import_csv_file_task.apply_async(
        args=[job_id],
        countdown=CONTACT_IMPORT_CLEANUP_DELAY_SECONDS,
    )


def schedule_call_log_export_file_cleanup(job_id: str, delay_seconds: int) -> None:
    cleanup_call_log_export_file_task.apply_async(
        args=[job_id],
        countdown=delay_seconds,
    )


def _mark_contact_import_canceled(job: ContactImportJob) -> None:
    _refresh_job(job)
    if job.status == ContactImportJob.Status.CANCELED:
        return
    job.status = ContactImportJob.Status.CANCELED
    job.completed_at = timezone.now()
    job.error_message = ""
    job.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
    _schedule_contact_import_file_cleanup(str(job.id))


def _mark_call_log_export_canceled(job: CallLogExportJob) -> None:
    _refresh_call_log_export_job(job)
    if job.status == CallLogExportJob.Status.CANCELED:
        return
    job.status = CallLogExportJob.Status.CANCELED
    job.completed_at = timezone.now()
    job.error_message = ""
    job.save(update_fields=["status", "completed_at", "error_message", "updated_at"])


def _contact_import_canceled(job: ContactImportJob) -> bool:
    _refresh_job(job)
    if not job.cancel_requested:
        return False
    _mark_contact_import_canceled(job)
    return True


def _call_log_export_canceled(job: CallLogExportJob) -> bool:
    _refresh_call_log_export_job(job)
    if not job.cancel_requested:
        return False
    _mark_call_log_export_canceled(job)
    return True


def _create_contacts_for_chunk(
    *, job: ContactImportJob, prepared_rows: list[PreparedContactRow]
) -> tuple[int, list[ContactImportFailure]]:
    if not prepared_rows:
        return 0, []

    contacts = [
        Contact(
            owner=job.owner,
            campaign=job.campaign,
            phone_number=prepared_row.phone_number,
            name=prepared_row.name,
            comments=prepared_row.comments,
            status=prepared_row.status,
        )
        for prepared_row in prepared_rows
    ]

    try:
        with transaction.atomic():
            Contact.objects.bulk_create(contacts, batch_size=CONTACT_IMPORT_BATCH_SIZE)
        return len(prepared_rows), []
    except IntegrityError:
        created_count = 0
        race_failures: list[ContactImportFailure] = []
        for prepared_row in prepared_rows:
            try:
                with transaction.atomic():
                    Contact.objects.create(
                        owner=job.owner,
                        campaign=job.campaign,
                        phone_number=prepared_row.phone_number,
                        name=prepared_row.name,
                        comments=prepared_row.comments,
                        status=prepared_row.status,
                    )
                created_count += 1
            except IntegrityError:
                race_failures.append(
                    _build_import_failure(
                        job=job,
                        row_number=prepared_row.row_number,
                        phone_number=prepared_row.phone_number,
                        row_data=prepared_row.row_data,
                        reason=CONTACT_IMPORT_DUPLICATE_REASON,
                    )
                )
        return created_count, race_failures


def _flush_contact_import_chunk(
    *,
    job: ContactImportJob,
    prepared_rows: list[PreparedContactRow],
    failures: list[ContactImportFailure],
    processed_count: int,
) -> None:
    existing_numbers: set[str] = set()
    if prepared_rows:
        phone_numbers = [prepared_row.phone_number for prepared_row in prepared_rows]
        existing_numbers = set(
            Contact.objects.filter(
                owner=job.owner,
                campaign=job.campaign,
                phone_number__in=phone_numbers,
            ).values_list("phone_number", flat=True)
        )

    contacts_to_create: list[PreparedContactRow] = []
    for prepared_row in prepared_rows:
        if prepared_row.phone_number in existing_numbers:
            failures.append(
                _build_import_failure(
                    job=job,
                    row_number=prepared_row.row_number,
                    phone_number=prepared_row.phone_number,
                    row_data=prepared_row.row_data,
                    reason=CONTACT_IMPORT_DUPLICATE_REASON,
                )
            )
            continue
        contacts_to_create.append(prepared_row)

    created_count, race_failures = _create_contacts_for_chunk(
        job=job,
        prepared_rows=contacts_to_create,
    )
    failures.extend(race_failures)

    if failures:
        ContactImportFailure.objects.bulk_create(
            failures,
            batch_size=CONTACT_IMPORT_BATCH_SIZE,
        )

    _refresh_job(job)
    job.processed_rows += processed_count
    job.created_count += created_count
    job.failed_count += len(failures)
    job.save(
        update_fields=[
            "processed_rows",
            "created_count",
            "failed_count",
            "updated_at",
        ]
    )


def _prepare_contact_row(
    *, job: ContactImportJob, row_number: int, row: dict[str, Any]
) -> tuple[PreparedContactRow | None, ContactImportFailure | None]:
    normalized_row = _normalize_import_row(row)
    serializer = ContactImportRowSerializer(
        data={
            "phone_number": normalized_row.get("phone_number", ""),
            "name": normalized_row.get("name", ""),
            "comments": normalized_row.get("comments", ""),
            "status": normalized_row.get("status", Contact.ContactStatus.NEW),
        }
    )
    if not serializer.is_valid():
        return None, _build_import_failure(
            job=job,
            row_number=row_number,
            phone_number=str(normalized_row.get("phone_number", "")),
            row_data=normalized_row,
            reason=_serialize_import_errors(serializer.errors),
        )

    validated_data = serializer.validated_data
    return (
        PreparedContactRow(
            row_number=row_number,
            phone_number=validated_data["phone_number"],
            name=validated_data["name"],
            comments=validated_data.get("comments") or "",
            status=validated_data.get("status", Contact.ContactStatus.NEW),
            row_data=normalized_row,
        ),
        None,
    )


def _count_contact_import_rows(job: ContactImportJob) -> int:
    total_rows = 0
    with job.csv_file.open("rb") as raw_file:
        wrapper = TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(wrapper)
        if reader.fieldnames is None or "phone_number" not in reader.fieldnames:
            raise ValueError("CSV must include a 'phone_number' column.")

        for total_rows, _ in enumerate(reader, start=1):
            if total_rows % CONTACT_IMPORT_BATCH_SIZE == 0 and _contact_import_canceled(
                job
            ):
                return total_rows

    return total_rows


def _call_log_export_queryset(job: CallLogExportJob):
    return (
        CallLog.objects.filter(owner=job.owner, campaign=job.campaign)
        .select_related("campaign")
        .annotate(derived_status=build_derived_status_expression())
        .order_by("created_at", "id")
    )


@shared_task(name="autodialer.tasks.process_contact_import_task")
def process_contact_import_task(job_id: str) -> dict[str, int | str]:
    job = (
        ContactImportJob.objects.select_related("owner", "campaign")
        .filter(pk=job_id)
        .first()
    )
    if job is None:
        return {"status": ContactImportJob.Status.FAILED}

    now = timezone.now()
    if job.cancel_requested:
        _mark_contact_import_canceled(job)
        return {"status": ContactImportJob.Status.CANCELED}

    job.status = ContactImportJob.Status.PREPARING
    job.started_at = job.started_at or now
    job.completed_at = None
    job.error_message = ""
    job.save(
        update_fields=[
            "status",
            "started_at",
            "completed_at",
            "error_message",
            "updated_at",
        ]
    )

    try:
        total_rows = _count_contact_import_rows(job)
        if job.status == ContactImportJob.Status.CANCELED:
            return {
                "status": ContactImportJob.Status.CANCELED,
                "processed_rows": job.processed_rows,
            }

        _refresh_job(job)
        job.total_rows = total_rows
        job.status = ContactImportJob.Status.PROCESSING
        job.save(update_fields=["total_rows", "status", "updated_at"])

        prepared_rows: list[PreparedContactRow] = []
        failures: list[ContactImportFailure] = []
        processed_count = 0
        local_seen_numbers: set[str] = set()

        with job.csv_file.open("rb") as raw_file:
            wrapper = TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(wrapper)

            for row_number, row in enumerate(reader, start=2):
                prepared_row, failure = _prepare_contact_row(
                    job=job,
                    row_number=row_number,
                    row=row,
                )
                if failure is not None:
                    failures.append(failure)
                elif prepared_row is not None:
                    if prepared_row.phone_number in local_seen_numbers:
                        failures.append(
                            _build_import_failure(
                                job=job,
                                row_number=prepared_row.row_number,
                                phone_number=prepared_row.phone_number,
                                row_data=prepared_row.row_data,
                                reason=CONTACT_IMPORT_DUPLICATE_REASON,
                            )
                        )
                    else:
                        local_seen_numbers.add(prepared_row.phone_number)
                        prepared_rows.append(prepared_row)

                processed_count += 1
                if processed_count < CONTACT_IMPORT_BATCH_SIZE:
                    continue

                _flush_contact_import_chunk(
                    job=job,
                    prepared_rows=prepared_rows,
                    failures=failures,
                    processed_count=processed_count,
                )
                prepared_rows = []
                failures = []
                processed_count = 0
                local_seen_numbers = set()

                if _contact_import_canceled(job):
                    return {
                        "status": ContactImportJob.Status.CANCELED,
                        "processed_rows": job.processed_rows,
                        "created_count": job.created_count,
                        "failed_count": job.failed_count,
                    }

        if processed_count:
            _flush_contact_import_chunk(
                job=job,
                prepared_rows=prepared_rows,
                failures=failures,
                processed_count=processed_count,
            )

        if _contact_import_canceled(job):
            return {
                "status": ContactImportJob.Status.CANCELED,
                "processed_rows": job.processed_rows,
                "created_count": job.created_count,
                "failed_count": job.failed_count,
            }

        _refresh_job(job)
        job.status = ContactImportJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "updated_at"])
        _schedule_contact_import_file_cleanup(str(job.id))
        return {
            "status": ContactImportJob.Status.COMPLETED,
            "processed_rows": job.processed_rows,
            "created_count": job.created_count,
            "failed_count": job.failed_count,
        }
    except Exception as exc:
        _refresh_job(job)
        if job.status != ContactImportJob.Status.CANCELED:
            job.status = ContactImportJob.Status.FAILED
            job.completed_at = timezone.now()
            job.error_message = str(exc)
            job.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )
            _schedule_contact_import_file_cleanup(str(job.id))
        raise


@shared_task(name="autodialer.tasks.process_call_log_export_task")
def process_call_log_export_task(job_id: str) -> dict[str, int | str]:
    job = (
        CallLogExportJob.objects.select_related("owner", "campaign")
        .filter(pk=job_id)
        .first()
    )
    if job is None:
        return {"status": CallLogExportJob.Status.FAILED}

    now = timezone.now()
    if job.cancel_requested:
        _mark_call_log_export_canceled(job)
        return {"status": CallLogExportJob.Status.CANCELED}

    job.status = CallLogExportJob.Status.PREPARING
    job.started_at = job.started_at or now
    job.completed_at = None
    job.first_downloaded_at = None
    job.expires_at = None
    job.error_message = ""
    job.save(
        update_fields=[
            "status",
            "started_at",
            "completed_at",
            "first_downloaded_at",
            "expires_at",
            "error_message",
            "updated_at",
        ]
    )

    temp_file_path: str | None = None
    try:
        total_rows = CallLog.objects.filter(
            owner=job.owner, campaign=job.campaign
        ).count()
        _refresh_call_log_export_job(job)
        if job.status == CallLogExportJob.Status.CANCELED:
            return {
                "status": CallLogExportJob.Status.CANCELED,
                "processed_rows": job.processed_rows,
            }

        job.total_rows = total_rows
        job.status = CallLogExportJob.Status.PROCESSING
        job.save(update_fields=["total_rows", "status", "updated_at"])

        last_created_at = None
        last_id = None

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            suffix=".csv",
            delete=False,
        ) as export_file:
            temp_file_path = export_file.name
            writer = csv.writer(export_file)
            writer.writerow(CALL_LOG_EXPORT_HEADERS)

            while True:
                queryset = _call_log_export_queryset(job)
                if last_created_at is not None and last_id is not None:
                    queryset = queryset.filter(
                        Q(created_at__gt=last_created_at)
                        | Q(created_at=last_created_at, id__gt=last_id)
                    )

                batch = list(queryset[:CALL_LOG_EXPORT_BATCH_SIZE])
                if not batch:
                    break

                for call_log in batch:
                    writer.writerow(build_call_log_export_row(call_log))
                export_file.flush()

                last_created_at = batch[-1].created_at
                last_id = batch[-1].id

                _refresh_call_log_export_job(job)
                job.processed_rows += len(batch)
                job.save(update_fields=["processed_rows", "updated_at"])

                if _call_log_export_canceled(job):
                    return {
                        "status": CallLogExportJob.Status.CANCELED,
                        "processed_rows": job.processed_rows,
                    }

        if _call_log_export_canceled(job):
            return {
                "status": CallLogExportJob.Status.CANCELED,
                "processed_rows": job.processed_rows,
            }

        with open(temp_file_path, "rb") as generated_file:
            if job.export_file:
                job.export_file.delete(save=False)
            job.export_file.save(
                job.original_filename
                or build_call_log_export_filename(job.campaign, job.started_at),
                File(generated_file),
                save=False,
            )

        completed_at = timezone.now()
        _refresh_call_log_export_job(job)
        job.status = CallLogExportJob.Status.COMPLETED
        job.completed_at = completed_at
        job.expires_at = completed_at + timedelta(
            seconds=CALL_LOG_EXPORT_RETENTION_SECONDS
        )
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "completed_at",
                "expires_at",
                "error_message",
                "export_file",
                "updated_at",
            ]
        )
        schedule_call_log_export_file_cleanup(
            str(job.id), CALL_LOG_EXPORT_RETENTION_SECONDS
        )
        return {
            "status": CallLogExportJob.Status.COMPLETED,
            "processed_rows": job.processed_rows,
            "total_rows": job.total_rows,
        }
    except Exception as exc:
        _refresh_call_log_export_job(job)
        if job.status != CallLogExportJob.Status.CANCELED:
            job.status = CallLogExportJob.Status.FAILED
            job.completed_at = timezone.now()
            job.error_message = str(exc)
            job.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )
        raise
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@shared_task(name="autodialer.tasks.cleanup_contact_import_csv_file_task")
def cleanup_contact_import_csv_file_task(job_id: str) -> dict[str, str]:
    job = ContactImportJob.objects.filter(pk=job_id).first()
    if job is None:
        return {"status": "missing"}
    if job.status not in CONTACT_IMPORT_TERMINAL_STATUSES:
        return {"status": "skipped"}
    if not job.csv_file:
        return {"status": "already_deleted"}

    job.csv_file.delete(save=False)
    job.csv_file = ""
    job.save(update_fields=["csv_file", "updated_at"])
    return {"status": "deleted"}


@shared_task(name="autodialer.tasks.cleanup_call_log_export_file_task")
def cleanup_call_log_export_file_task(job_id: str) -> dict[str, str]:
    job = CallLogExportJob.objects.filter(pk=job_id).first()
    if job is None:
        return {"status": "missing"}
    if job.status not in CALL_LOG_EXPORT_TERMINAL_STATUSES:
        return {"status": "skipped"}
    if not job.export_file:
        return {"status": "already_deleted"}
    if job.expires_at and job.expires_at > timezone.now():
        return {"status": "waiting"}

    job.export_file.delete(save=False)
    job.export_file = ""
    job.save(update_fields=["export_file", "updated_at"])
    return {"status": "deleted"}


@shared_task(name="autodialer.tasks.cleanup_stale_contact_import_csv_files")
def cleanup_stale_contact_import_csv_files() -> int:
    cutoff = timezone.now() - timedelta(seconds=CONTACT_IMPORT_CLEANUP_DELAY_SECONDS)
    stale_jobs = ContactImportJob.objects.filter(
        status__in=CONTACT_IMPORT_TERMINAL_STATUSES,
        completed_at__isnull=False,
        completed_at__lte=cutoff,
    ).filter(~Q(csv_file=""))

    deleted_count = 0
    for job_id in stale_jobs.values_list("id", flat=True):
        result = cleanup_contact_import_csv_file_task(str(job_id))
        if result["status"] == "deleted":
            deleted_count += 1
    return deleted_count


@shared_task(name="autodialer.tasks.cleanup_stale_call_log_export_files")
def cleanup_stale_call_log_export_files() -> int:
    stale_jobs = CallLogExportJob.objects.filter(
        status__in=CALL_LOG_EXPORT_TERMINAL_STATUSES,
        expires_at__isnull=False,
        expires_at__lte=timezone.now(),
    ).filter(~Q(export_file=""))

    deleted_count = 0
    for job_id in stale_jobs.values_list("id", flat=True):
        result = cleanup_call_log_export_file_task(str(job_id))
        if result["status"] == "deleted":
            deleted_count += 1
    return deleted_count


@shared_task(name="autodialer.tasks.activate_due_campaigns")
def activate_due_campaigns() -> int:
    now = timezone.now()
    activated_count = 0
    due_campaigns = Campaign.objects.filter(
        status__in=[
            Campaign.CampaignStatus.NEW,
            Campaign.CampaignStatus.SCHEDULED,
            Campaign.CampaignStatus.OVERDUE,
        ],
        scheduled_at__isnull=False,
        scheduled_at__lte=now,
    ).select_related("owner")

    for campaign in due_campaigns:
        has_audio = hasattr(campaign, "audio")
        has_contacts = campaign.contacts.filter(
            status__in=[Contact.ContactStatus.NEW, Contact.ContactStatus.ACTIVE]
        ).exists()
        if not has_audio or not has_contacts or not campaign.owner.access_token:
            if campaign.status != Campaign.CampaignStatus.OVERDUE:
                campaign.status = Campaign.CampaignStatus.OVERDUE
                campaign.save(update_fields=["status", "updated_at"])
            continue

        campaign.status = Campaign.CampaignStatus.PROCESSING
        campaign.started_at = campaign.started_at or now
        campaign.save(update_fields=["status", "started_at", "updated_at"])
        dispatch_campaign_calls(campaign)
        activated_count += 1

    return activated_count


@shared_task(name="autodialer.tasks.dispatch_campaign_calls_task")
def dispatch_campaign_calls_task(campaign_id: str) -> list[str]:
    campaign = Campaign.objects.select_related("owner").filter(pk=campaign_id).first()
    if campaign is None:
        return []
    return [str(call_log_id) for call_log_id in dispatch_campaign_calls(campaign)]


@shared_task(name="autodialer.tasks.pump_processing_campaigns")
def pump_processing_campaigns() -> int:
    processed = 0
    for campaign in Campaign.objects.filter(
        status=Campaign.CampaignStatus.PROCESSING
    ).select_related("owner"):
        dispatch_campaign_calls(campaign)
        maybe_finish_campaign(campaign)
        processed += 1
    return processed


@shared_task(name="autodialer.tasks.play_campaign_audio_task")
def play_campaign_audio_task(call_log_id: str) -> None:
    from autodialer.models import CallLog

    call_log = (
        CallLog.objects.select_related("owner", "campaign")
        .filter(pk=call_log_id)
        .first()
    )
    if call_log is None:
        return
    play_campaign_audio(call_log)
