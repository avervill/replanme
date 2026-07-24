# Resched.me

Resched.me is an AI-assisted planning app for structuring your week, month, and year. This scaffold sets up:

- A `Next.js + Tailwind CSS` frontend with a dashboard-style landing page and AI side panel.
- A `FastAPI` backend with routes for calendar planning, Google integration stubs, energy-based scheduling, voice parsing, and image-to-calendar import previews.
- `Postgres` and `Redis` local infrastructure via Docker Compose.

## Project structure

```text
resched-me/
  apps/
    api/   FastAPI backend
    web/   Next.js frontend
```

## Included product foundations

- Google Calendar connection flow placeholder
- AI planning endpoint structure
- Energy-based scheduling preview logic
- Voice-to-calendar parsing endpoint
- Image-to-text schedule import preview endpoint
- Manual calendar editing API contract

## Quick start

1. Copy the environment file:

```powershell
Copy-Item .env.example .env
```

2. Start the supporting services:

```powershell
docker compose up postgres redis -d
```

3. Start the API:

```powershell
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload
```

4. Start the frontend:

```powershell
cd apps/web
npm install
npm run dev
```

## Docker-based dev

You can also run the whole stack with:

```powershell
docker compose up --build
```
