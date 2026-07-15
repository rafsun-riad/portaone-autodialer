# PortaOne Autodialer Instructions

- Frontend lives in `frontend/` and uses the Next.js App Router. Keep `page.tsx` files and layouts as server components by default; introduce client components only for interactive islands.
- Frontend state rules: use React Query for backend data fetching and cache invalidation, Zustand for shared UI/session state, and React Hook Form for forms.
- Prefer the existing proxy/auth routes under `frontend/app/api/` when adding new frontend-to-backend calls so PortaOne session cookies remain the source of truth.
- Use Bangladesh time (`Asia/Dhaka`) for campaign scheduling and display. Do not introduce per-user timezone logic unless asked.
- Backend lives in `backend/` and uses Django + DRF. Keep the design simple and stable; avoid over-engineering.
- External customer data must remain deduplicated by the saved PortaOne user identity. Replace the stored JSON payload on sync instead of creating duplicate user records.
- Webhook payloads should remain persisted for inquiry: playback callbacks go to text logs, and call state payloads should keep updating the database record for the corresponding call.
- Campaign media is local Django file storage for now. Keep supported upload formats to `.wav` and `.mp3` unless requirements change.
