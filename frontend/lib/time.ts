import { formatInTimeZone, fromZonedTime } from "date-fns-tz";

import { APP_TIMEZONE } from "@/lib/env";

export function toDhakaInputValue(value?: string | null) {
  if (!value) {
    return "";
  }

  return formatInTimeZone(value, APP_TIMEZONE, "yyyy-MM-dd'T'HH:mm");
}

export function fromDhakaInputValue(value: string) {
  if (!value) {
    return null;
  }

  return fromZonedTime(value, APP_TIMEZONE).toISOString();
}

export function formatDhakaDateTime(value?: string | null) {
  if (!value) {
    return "Not scheduled";
  }

  return formatInTimeZone(value, APP_TIMEZONE, "dd MMM yyyy, hh:mm a");
}
