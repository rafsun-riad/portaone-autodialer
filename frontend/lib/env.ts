export const BACKEND_API_ORIGIN =
  process.env.BACKEND_API_ORIGIN ??
  process.env.NEXT_PUBLIC_BACKEND_API_ORIGIN ??
  "http://localhost:8000";

export const EXTERNAL_SYSTEM_ORIGIN =
  process.env.EXTERNAL_SYSTEM_ORIGIN ??
  process.env.NEXT_PUBLIC_EXTERNAL_SYSTEM_ORIGIN ??
  "http://localhost:8080";

export const APP_TIMEZONE = "Asia/Dhaka";
