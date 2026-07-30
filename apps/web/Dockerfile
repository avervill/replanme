FROM node:22-alpine

ARG API_ORIGIN=http://api:8000

ENV NEXT_TELEMETRY_DISABLED=1 \
    API_ORIGIN=$API_ORIGIN \
    PORT=3000

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web ./
RUN npm run build

CMD ["sh", "-c", "npm run start -- --hostname 0.0.0.0 --port ${PORT:-3000}"]
