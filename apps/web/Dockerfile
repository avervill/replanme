FROM node:20-alpine

ENV NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

CMD ["sh", "-c", "npm run start -- --hostname 0.0.0.0 --port ${PORT:-3000}"]
