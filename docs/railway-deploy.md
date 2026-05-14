# Railway Deployment

This repo is a monorepo with two deployable Railway services:

- `replanme-api` from `apps/api`
- `replanme-web` from `apps/web`

Railway's monorepo guide recommends setting a root directory per service. If you use config-as-code, point each service to the matching config file:

- API config: `/apps/api/railway.toml`
- Web config: `/apps/web/railway.toml`

## Services

Create these Railway services in one project:

1. PostgreSQL plugin
2. Redis plugin
3. API service from the GitHub repo
4. Web service from the same GitHub repo

Set the API service root directory to:

```text
apps/api
```

Set the Web service root directory to:

```text
apps/web
```

Both services use Dockerfiles. The API container starts Uvicorn and the app creates missing tables on startup through its existing `init_db()` path. The Web container builds Next.js and starts `next start`.

## API Variables

Set these on the API service:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
SECRET_KEY=<generate-a-long-random-secret>
FRONTEND_URL=https://<your-web-domain>
OPENAI_API_KEY=<your-openai-key>
OPENAI_MODEL=gpt-4o-mini
AI_SIMPLE_MODEL=gpt-4o-mini
AI_COMPLEX_MODEL=gpt-5.4-mini
WHISPER_MODEL=gpt-4o-mini-transcribe
GOOGLE_CLIENT_ID=<google-oauth-client-id>
GOOGLE_CLIENT_SECRET=<google-oauth-client-secret>
GOOGLE_REDIRECT_URI=https://<your-api-domain>/api/v1/auth/google/callback
ADMIN_EMAILS=<optional-comma-separated-admin-emails>
```

Railway Postgres may expose `DATABASE_URL` as `postgres://` or `postgresql://`; the app normalizes it to `postgresql+asyncpg://` at startup.

## Web Variables

Set this on the Web service before building:

```text
NEXT_PUBLIC_API_BASE_URL=https://<your-api-domain>/api/v1
```

`NEXT_PUBLIC_API_BASE_URL` is used by the browser bundle, so redeploy the Web service after changing it.

## Google OAuth

In Google Cloud Console, add this authorized redirect URI:

```text
https://<your-api-domain>/api/v1/auth/google/callback
```

The API `GOOGLE_REDIRECT_URI` must match exactly.

## Healthchecks

API:

```text
/api/v1/health
```

Web:

```text
/
```

## Deployment Order

1. Provision Postgres and Redis.
2. Deploy API with all backend variables.
3. Copy the API public domain.
4. Set `NEXT_PUBLIC_API_BASE_URL` on Web.
5. Deploy Web.
6. Copy the Web public domain.
7. Set `FRONTEND_URL` on API to the Web public domain.
8. Redeploy API so CORS uses the production frontend domain.

## Local Docker Smoke Test

From the repo root:

```powershell
docker compose up --build
```

For production-like container commands:

```powershell
docker build -t replanme-api ./apps/api
docker build -t replanme-web ./apps/web
```
