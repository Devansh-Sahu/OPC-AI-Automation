# =============================================================================
# OpenSource AI Engineer — Backend Dockerfile
# Multi-stage build: base → deps → production
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: base — system dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS base

LABEL maintainer="OpenSource AI Engineer"
LABEL description="FastAPI backend for OpenSource AI Engineer"

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    gcc \
    g++ \
    make \
    # PostgreSQL client library
    libpq-dev \
    # Git (for repo cloning agent)
    git \
    # cURL (for healthcheck + HTTP calls)
    curl \
    # SSL certificates
    ca-certificates \
    # Required for some Python packages
    libffi-dev \
    libssl-dev \
    # Tree-sitter build deps
    libc6-dev \
    # Diff tools
    diffutils \
    patch \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: deps — Python dependency installation
# -----------------------------------------------------------------------------
FROM base AS deps

# Copy requirements first (Docker layer caching)
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Install tree-sitter language grammars
# These are used by the Repository Analyzer agent for AST-based code chunking
RUN python -c "\
import subprocess, sys; \
packages = [ \
    'tree-sitter-python', \
    'tree-sitter-javascript', \
    'tree-sitter-typescript', \
    'tree-sitter-go', \
    'tree-sitter-rust', \
    'tree-sitter-java', \
    'tree-sitter-c', \
    'tree-sitter-cpp', \
    'tree-sitter-ruby', \
    'tree-sitter-kotlin', \
]; \
subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + packages)" || \
    echo "Warning: some tree-sitter grammars failed to install — continuing"

# -----------------------------------------------------------------------------
# Stage 3: production — final slim image
# -----------------------------------------------------------------------------
FROM base AS production

# Copy installed Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source
COPY --chown=appuser:appgroup backend/ ./backend/
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./alembic.ini
COPY --chown=appuser:appgroup scripts/ ./scripts/

# Create required runtime directories
RUN mkdir -p /tmp/repos /app/logs && \
    chown -R appuser:appgroup /tmp/repos /app/logs

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command — uvicorn with 4 workers
# Worker count can be overridden via docker-compose command
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "info", \
     "--access-log", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
