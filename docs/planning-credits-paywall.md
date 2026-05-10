# Planning Credits and Paywall

## Plans

Free users receive 20 signup planning credits and a lazy weekly refill of 5 credits, capped at 30. Pro users receive a lazy monthly refill of 300 credits, capped at 300. Admin users can be managed manually and do not receive automatic refill changes.

Google Calendar connection and manual calendar create/edit/delete remain free. AI planning and AI calendar actions are checked by the backend before expensive work runs.

## Credit Costs

Credit costs are centralized in `apps/api/app/services/billing_config.py`.

- Quick add and single event move/update/delete: 1
- Duplicate day: 2
- Duplicate week: 4
- Optimize day: 3
- Optimize week: 5
- Plan day: 3
- Plan week: 5
- Plan month: 10
- Image-to-calendar: 5
- Voice-to-calendar: 2
- Regenerate plan: 2
- Complex multi-step action: 5

## Spending Rules

Credits are checked before expensive AI work and spent only after successful AI processing, direct calendar application, or draft generation. Failed AI work does not deduct credits. Applying an already-paid draft is free.

Plain uploads are free. Image extraction and voice transcription are credit-gated when processing succeeds.

## Paywall Reasons

- `NO_CREDITS`
- `NOT_ENOUGH_CREDITS`
- `FEATURE_LOCKED`
- `MONTHLY_LIMIT_REACHED`
- `SUBSCRIPTION_INACTIVE`

The API returns structured paywall payloads with required credits, available credits, and UI copy.

## Admin

Set admin users locally with:

```env
ADMIN_EMAILS=admin@example.com,owner@example.com
```

Admins can open `/admin`, grant credits, adjust balances, set plans, and inspect credit transactions and planning requests. Admin adjustments require a reason and always create a transaction.

## Local Testing

Manual checklist:

- New Google login receives 20 signup credits and a `signup_bonus` transaction.
- Free user weekly refill adds at most 5 credits and caps at 30.
- Pro monthly refill caps at 300.
- AI planning with enough credits succeeds and creates a deduct transaction.
- Failed AI planning does not deduct credits.
- Insufficient credits returns a structured paywall response.
- Manual calendar CRUD works with 0 credits.
- Image upload stores the file without spending credits.
- Voice transcription spends credits only after a transcript is returned.
- Non-admin users cannot access `/api/v1/admin/*`.
- Admin grant and adjustment create before/after transaction rows.

## Future Stripe

The schema includes Stripe customer and subscription IDs, but no fake payment flow is implemented. Stripe checkout/webhooks can later update `plan`, `subscription_status`, `subscription_provider`, and subscription period fields, then call the existing Pro monthly credit grant logic.
