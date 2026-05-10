# Admin Analytics MVP

## What Is Tracked

Internal analytics are stored in `analytics_events` and related operational tables:

- `user_signed_up`
- `user_logged_in`
- `google_calendar_connected`
- `ai_prompt_submitted`
- `planning_draft_created`
- `planning_applied_to_calendar`
- `planning_failed`
- `credits_granted`
- `credits_used`
- `manual_calendar_event_created`
- `manual_calendar_event_updated`
- `manual_calendar_event_deleted`
- `image_uploaded_to_calendar`
- `voice_prompt_used`
- `onboarding_started`
- `onboarding_completed`
- `paywall_viewed`
- `upgrade_clicked`

Planning request details live in `planning_requests`. Credit balance changes live in `credit_transactions`.

## Planning Credits

Credits are centralized in the backend. Admin grants and adjustments update `users.planning_credits` and always create a credit transaction. Normal AI deductions are created only after successful paid AI work.

## Admin Access

Set admin users with:

```env
ADMIN_EMAILS=your@email.com
```

On login or profile refresh, matching users are treated as admins. Admin API routes also check the authenticated user server-side.

## Admin Routes

- `/admin`
- `/admin/users/:userId`

## Admin API

All endpoints are under `/api/v1/admin`:

- `GET /analytics/overview`
- `GET /analytics/timeseries?range=14d|30d`
- `GET /users?page=1&pageSize=25&search=&sort=createdAt`
- `GET /users/:userId`
- `GET /users/:userId/credit-transactions`
- `GET /users/:userId/planning-requests`
- `POST /users/:userId/credits/grant`
- `POST /users/:userId/credits/adjust`
- `POST /users/:userId/plan`

Upgrade clicks are tracked through `POST /api/v1/subscription/upgrade-clicked`.

## Manual Test Checklist

- Log in with an email in `ADMIN_EMAILS` and open `/admin`.
- Confirm overview cards show real counts, not placeholder numbers.
- Search users by email or name.
- Filter users by admin, Google Calendar connection, and recent activity.
- Open a user detail page.
- Grant credits with a positive amount and reason.
- Adjust credits with a positive or negative amount and reason.
- Confirm credit transaction history refreshes with before/after balances.
- Log in as a non-admin and confirm `/admin` redirects or admin APIs return 403.
- Create, update, and delete a manual calendar event; confirm analytics rows are created.
- Click an upgrade button; confirm `upgrade_clicked` is tracked.
