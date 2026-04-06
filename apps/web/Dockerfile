# ── Development stage ─────────────────────────────────────────────────
FROM node:20-alpine AS development

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

COPY . .

CMD ["npm", "run", "dev"]

# ── Build stage ──────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# NEXT_PUBLIC_* vars are baked at build time by Next.js
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

COPY package.json package-lock.json* ./
# npm ci requires 100% lockfile consistency.
# Fallback to `npm install` if lockfile is out of sync (e.g., new deps added
# to package.json but lockfile not regenerated). After fixing the lockfile
# locally (`npm install --legacy-peer-deps && git commit package-lock.json`),
# switch back to `npm ci` for fully reproducible builds.
RUN npm install --legacy-peer-deps --ignore-scripts && npm cache clean --force

COPY . .
RUN npm run build

# ── Production stage ─────────────────────────────────────────────────
FROM node:20-alpine AS production

# Security: run as non-root
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

WORKDIR /app

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

ENV HOSTNAME="0.0.0.0"
ENV NODE_ENV=production

CMD ["node", "server.js"]
