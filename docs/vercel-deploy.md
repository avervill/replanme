# Vercel full-stack deployment

Replanme uses two Vercel projects from the same monorepo:

- `apps/web` — Next.js frontend at `replanme.vercel.app`
- `apps/api` — FastAPI on the Vercel Python runtime
- Neon Marketplace integration — serverless Postgres
- Upstash Marketplace integration — serverless Redis

## API project

Create a Vercel project named `replanme-api` with `apps/api` as its root. Vercel detects `app.py`, imports `app.main:app`, and deploys the entire FastAPI application as one streaming Python Function.

Connect free Neon and Upstash resources from Vercel Marketplace. Keep Upstash auto-upgrade disabled. Marketplace injects the database credentials into the API project without committing secrets.

## Required variables

```dotenv
ENVIRONMENT=production
DATABASE_URL=<Neon pooled Postgres URL>
REDIS_URL=<Upstash Redis TLS URL>
FRONTEND_URL=https://replanme.vercel.app
COOKIE_SECURE=true
TOKEN_ENCRYPTION_KEY=<Fernet key>
MAX_UPLOAD_BYTES=4000000

OPENAI_API_KEY=<server-side secret>
AI_SIMPLE_MODEL=gpt-5.6-luna
AI_COMPLEX_MODEL=gpt-5.6-terra
TRANSCRIPTION_MODEL=gpt-transcribe

GOOGLE_CLIENT_ID=<Google OAuth client>
GOOGLE_CLIENT_SECRET=<Google OAuth secret>
GOOGLE_REDIRECT_URI=https://replanme.vercel.app/api/v1/auth/google/callback
GOOGLE_ALLOWED_EMAILS=<comma-separated test users>
```

## Database baseline

Run the migration against the production database before enabling authenticated traffic:

```sh
cd apps/api
vercel env pull .env.production.local --environment=production
uv run --env-file .env.production.local alembic upgrade head
```

Do not reuse a previous database: v1 starts from the clean Alembic baseline and test users authenticate again.

## Web handoff

Set these variables on the `replanme` web project:

```dotenv
API_ORIGIN=https://replanme-api.vercel.app
NEXT_PUBLIC_SITE_URL=https://replanme.vercel.app
```

All browser requests stay on the frontend origin under `/api/v1`. The Next.js rewrite forwards them to the API Function, so the opaque session cookie remains first-party.

## Platform constraints

- Vercel Hobby Functions are serverless and can cold-start, but the public landing page and `/demo` remain static and immediately available.
- Function request and response bodies are limited to 4.5 MB, so production image and voice uploads use `MAX_UPLOAD_BYTES=4000000`.
- SSE responses are supported by the Vercel Python runtime, but they are bounded by the Function duration.
- Uploads are processed in memory and never rely on the ephemeral filesystem.
