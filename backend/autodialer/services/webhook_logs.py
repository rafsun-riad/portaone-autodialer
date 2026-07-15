from __future__ import annotations

import json
from datetime import datetime

from django.conf import settings


def append_webhook_payload(filename: str, payload: dict) -> str:
    settings.WEBHOOK_LOG_DIR.mkdir(parents=True, exist_ok=True)
    target_path = settings.WEBHOOK_LOG_DIR / filename
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    with target_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {json.dumps(payload, ensure_ascii=True)}\n")
    return str(target_path)
