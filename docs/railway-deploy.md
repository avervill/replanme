# Railway API deployment

Deploy only the API and data services on Railway; the Next.js frontend belongs on Vercel.

## Services

1. Create a Railway project from this repository.
2. Add a PostgreSQL service and a Redis service with fresh volumes.
3. Add an API service using repository root `.` and `apps/api/Dockerfile`.
4. Set `/api/v1/health` as the healthcheck.

The image starts with:

```sh
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

## Required variables

```dotenv
ENVIRONMENT=production
DATABASE_URL=<Railway Postgres URL>
REDIS_URL=<Railway Redis URL>
FRONTEND_URL=https://<vercel-production-domain>
COOKIE_SECURE=true
TOKEN_ENCRYPTION_KEY=<Fernet key>

OPENAI_API_KEY=<server-side secret>
AI_SIMPLE_MODEL=gpt-5.6-luna
AI_COMPLEX_MODEL=gpt-5.6-terra
TRANSCRIPTION_MODEL=gpt-transcribe

GOOGLE_CLIENT_ID=<Google OAuth client>
GOOGLE_CLIENT_SECRET=<Google OAuth secret>
GOOGLE_REDIRECT_URI=https://<vercel-production-domain>/api/v1/auth/google/callback
GOOGLE_ALLOWED_EMAILS=<comma-separated test users>
```

## Vercel handoff

Set `API_ORIGIN=https://<railway-api-domain>` as a server-only Vercel variable. All browser requests stay on the Vercel origin under `/api/v1`; the rewrite forwards them to Railway and keeps the session cookie first-party.

Do not reuse a previous database: v1 starts from the clean Alembic baseline and test users authenticate again.
