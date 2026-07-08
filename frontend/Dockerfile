# ============================================================
# VERTEX frontend — Next.js 14 dashboard.
#
# NOTE: NEXT_PUBLIC_API_URL is baked in at BUILD time (Next inlines NEXT_PUBLIC_*
# into the client bundle). It must be a URL the user's BROWSER can reach — i.e. the
# host-published backend port (http://localhost:8000), NOT the internal service name.
# ============================================================
FROM node:18-alpine

# Where the browser will reach the backend API. Override at build:
#   docker compose build --build-arg NEXT_PUBLIC_API_URL=https://api.example.com frontend
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# Install deps first (better layer caching).
COPY package.json package-lock.json* ./
RUN npm install

# Build the production bundle.
COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
