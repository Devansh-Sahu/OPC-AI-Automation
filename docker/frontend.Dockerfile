# =============================================================================
# OpenSource AI Engineer — Frontend Dockerfile
# Multi-stage build: deps → builder → runner
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: deps — dependency installation
# -----------------------------------------------------------------------------
FROM node:20-alpine AS deps

# Install libc compatibility for some native modules
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy dependency manifests
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

# Install dependencies using the available lockfile
RUN \
  if [ -f yarn.lock ]; then yarn --frozen-lockfile; \
  elif [ -f package-lock.json ]; then npm ci; \
  elif [ -f pnpm-lock.yaml ]; then \
    corepack enable pnpm && pnpm i --frozen-lockfile; \
  else npm install; \
  fi

# -----------------------------------------------------------------------------
# Stage 2: builder — Next.js production build
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Build-time arguments (baked into static assets)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

# Copy installed node_modules from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy all application source files
COPY . .

# Disable Next.js telemetry during build
ENV NEXT_TELEMETRY_DISABLED=1

# Build the Next.js application
RUN \
  if [ -f yarn.lock ]; then yarn build; \
  elif [ -f package-lock.json ]; then npm run build; \
  elif [ -f pnpm-lock.yaml ]; then \
    corepack enable pnpm && pnpm run build; \
  else npm run build; \
  fi

# -----------------------------------------------------------------------------
# Stage 3: runner — minimal production image
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runner

LABEL maintainer="OpenSource AI Engineer"
LABEL description="Next.js frontend dashboard for OpenSource AI Engineer"

WORKDIR /app

# Security: run as non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Set production environment
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Copy only the production artifacts from builder
# public/ — static assets
COPY --from=builder /app/public ./public

# Copy the standalone server output (requires output: 'standalone' in next.config.js)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Switch to non-root user
USER nextjs

# Expose dashboard port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3000/api/health || exit 1

# Start the Next.js server
CMD ["node", "server.js"]
