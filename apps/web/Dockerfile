FROM node:20-alpine

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    PORT=3000

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web ./
RUN npm run build

CMD ["sh", "-c", "npm run start -- --hostname 0.0.0.0 --port ${PORT:-3000}"]
