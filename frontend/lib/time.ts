import { formatInTimeZone, fromZonedTime } from "date-fns-tz";

import { APP_TIMEZONE } from "@/lib/env";

const RECEIVED_TIME_OFFSET_MS = 6 * 60 * 60 * 1000;

function parseTimestampWithOptionalShortOffset(value: string) {
  const normalizedValue = value
    .trim()
    .replace(" ", "T")
    .replace(/([+-]\d{2})$/, "$1:00");

  const parsed = new Date(normalizedValue);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

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

export function formatDhakaDateTimeWithSeconds(value?: string | null) {
  if (!value) {
    return "-";
  }

  return formatInTimeZone(value, APP_TIMEZONE, "dd MMM yyyy, hh:mm:ss a");
}

export function formatDhakaReceivedCallLogTime(value?: string | null) {
  if (!value) {
    return "-";
  }

  const parsed = parseTimestampWithOptionalShortOffset(value);
  if (!parsed) {
    return formatDhakaDateTimeWithSeconds(value);
  }

  return formatInTimeZone(
    new Date(parsed.getTime() + RECEIVED_TIME_OFFSET_MS),
    APP_TIMEZONE,
    "dd MMM yyyy, hh:mm:ss a",
  );
}
