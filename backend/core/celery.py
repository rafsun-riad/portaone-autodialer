from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.timezone = "Asia/Dhaka"
app.conf.beat_schedule = {
    "activate-due-campaigns-every-minute": {
        "task": "autodialer.tasks.activate_due_campaigns",
        "schedule": 60.0,
    },
    "pump-processing-campaigns-every-minute": {
        "task": "autodialer.tasks.pump_processing_campaigns",
        "schedule": 60.0,
    },
    "cleanup-stale-contact-import-files-every-5-minutes": {
        "task": "autodialer.tasks.cleanup_stale_contact_import_csv_files",
        "schedule": 300.0,
    },
    "cleanup-stale-call-log-export-files-every-5-minutes": {
        "task": "autodialer.tasks.cleanup_stale_call_log_export_files",
        "schedule": 300.0,
    },
}
