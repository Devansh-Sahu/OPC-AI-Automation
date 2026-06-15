# =============================================================================
# OpenSource AI Engineer — Sandbox Dockerfile
# Isolated execution environment for untrusted AI-generated code
#
# Security design:
#   - Non-root user (agent, uid 1000)
#   - No network access enforced at runtime via docker run --network=none
#   - Read-only filesystem except /workspace (enforced via docker run --read-only)
#   - Resource limits enforced via docker run --memory --cpus --pids-limit
#   - No privilege escalation (no-new-privileges security opt)
#   - Supports: Python, JavaScript/Node, Go, Rust
# =============================================================================

FROM python:3.12-slim AS sandbox

LABEL maintainer="OpenSource AI Engineer"
LABEL description="Isolated sandbox for executing AI-generated code"
LABEL security.no-network="true"
LABEL security.no-root="true"

# Prevent interactive prompts and set sensible Python defaults
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONSAFEPATH=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/agent/.cargo/bin:/usr/local/go/bin:$PATH" \
    GOPATH=/home/agent/go \
    GOCACHE=/tmp/go-cache \
    CARGO_HOME=/home/agent/.cargo \
    RUSTUP_HOME=/home/agent/.rustup \
    NODE_ENV=test \
    npm_config_cache=/tmp/npm-cache

# Install system dependencies and runtimes
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    gcc \
    g++ \
    make \
    # Git (needed by some test frameworks)
    git \
    # cURL (for health probes)
    curl \
    # SSL certs
    ca-certificates \
    # Node.js 20.x
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    # Go 1.22
    && curl -fsSL https://golang.org/dl/go1.22.4.linux-amd64.tar.gz -o /tmp/go.tar.gz \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root sandbox user
RUN groupadd --gid 1000 agent && \
    useradd --uid 1000 --gid agent --shell /bin/bash --create-home agent

# Create workspace directory (the only writable mount point)
RUN mkdir -p /workspace /tmp/sandbox-output && \
    chown -R agent:agent /workspace /tmp/sandbox-output /tmp

# Install Rust toolchain as agent user (for Rust code execution)
USER agent
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
    sh -s -- -y --default-toolchain stable --profile minimal 2>/dev/null || \
    echo "Warning: Rust installation failed — Rust sandbox support unavailable"

# Install Python test frameworks and common packages
RUN pip install --user --no-cache-dir \
    # Testing
    pytest==8.2.2 \
    pytest-asyncio==0.23.7 \
    pytest-cov==5.0.0 \
    pytest-mock==3.14.0 \
    pytest-timeout==2.3.1 \
    hypothesis==6.103.1 \
    # Common dev packages (pre-installed for faster test runs)
    httpx==0.27.0 \
    requests==2.32.3 \
    aiohttp==3.9.5 \
    pydantic==2.7.4 \
    sqlalchemy==2.0.30 \
    alembic==1.13.1 \
    # Data science basics
    numpy==1.26.4 \
    pandas==2.2.2 \
    # Linting/formatting (used by review agent)
    ruff==0.4.9 \
    black==24.4.2 \
    mypy==1.10.0 \
    bandit==1.7.9

# Install Node.js test frameworks globally
USER root
RUN npm install -g --no-audit --no-fund \
    jest@29.7.0 \
    @jest/globals@29.7.0 \
    vitest@1.6.0 \
    mocha@10.4.0 \
    chai@5.1.1 \
    typescript@5.4.5 \
    ts-node@10.9.2 \
    eslint@8.57.0 \
    2>/dev/null || echo "Warning: some npm packages failed to install"

# Set correct ownership
RUN chown -R agent:agent /home/agent

# Switch back to non-root agent user
USER agent
WORKDIR /workspace

# Verify installations
RUN python --version && \
    node --version && \
    npm --version && \
    go version && \
    echo "Sandbox runtime check: OK"

# Sandbox is launched per-job by the worker service
# It does NOT have a long-running CMD — it's invoked via:
#   docker run --rm --network=none --read-only \
#     --tmpfs /tmp:size=128m,noexec \
#     --memory=512m --cpus=1 --pids-limit=128 \
#     --security-opt=no-new-privileges \
#     -v /tmp/repos/<run_id>:/workspace:ro \
#     -v /tmp/sandbox-output/<run_id>:/tmp/sandbox-output:rw \
#     ose_sandbox python -m pytest /workspace/tests/ --timeout=60
CMD ["/bin/bash"]
