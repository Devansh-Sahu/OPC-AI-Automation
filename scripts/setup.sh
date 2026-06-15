#!/usr/bin/env bash
# =============================================================================
# OpenSource AI Engineer — One-Command Setup Script
# =============================================================================
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
#
# What this script does:
#   1. Checks all prerequisites (Docker, Docker Compose, Python 3, curl)
#   2. Generates .env from .env.example with secure random keys
#   3. Builds all Docker images
#   4. Starts infrastructure services (postgres, redis, chromadb)
#   5. Runs database migrations (alembic upgrade head)
#   6. Seeds initial data (GSoC orgs, CNCF projects)
#   7. Starts all remaining services (backend, worker, frontend)
#   8. Displays status and next steps
# =============================================================================
set -euo pipefail

# =============================================================================
# COLORS & FORMATTING
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $*${NC}"; }
error()   { echo -e "${RED}❌ $*${NC}"; }
header()  { echo -e "\n${BOLD}${BLUE}$*${NC}\n"; }

# =============================================================================
# CONFIGURATION
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"

# Detect docker compose command (v1 vs v2)
if command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE=""
fi

# =============================================================================
# BANNER
# =============================================================================
echo ""
echo -e "${BOLD}${BLUE}"
echo "  ╔═══════════════════════════════════════════════════════╗"
echo "  ║         🤖  OpenSource AI Engineer  🤖                ║"
echo "  ║         Autonomous PR Generation System               ║"
echo "  ╚═══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# =============================================================================
# STEP 0: PREREQUISITES CHECK
# =============================================================================
header "Step 0: Checking prerequisites..."

PREREQ_FAILED=0

# Docker
if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
    success "Docker found: $DOCKER_VERSION"
else
    error "Docker is required but not installed."
    echo "  Install Docker Desktop: https://docs.docker.com/get-docker/"
    PREREQ_FAILED=1
fi

# Docker Compose
if [[ -n "$DOCKER_COMPOSE" ]]; then
    success "Docker Compose found: $DOCKER_COMPOSE"
else
    error "Docker Compose is required but not installed."
    echo "  Install: https://docs.docker.com/compose/install/"
    PREREQ_FAILED=1
fi

# Python 3 (for key generation)
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    success "Python 3 found: $PY_VERSION"
elif command -v python &>/dev/null; then
    PY_VERSION=$(python --version 2>&1 | awk '{print $2}')
    if [[ "$PY_VERSION" == 3* ]]; then
        success "Python 3 found: $PY_VERSION"
        alias python3='python'
    else
        warning "Python 3 not found — will skip key auto-generation"
    fi
else
    warning "Python 3 not found — will skip key auto-generation"
fi

# curl (used inside containers, just checking if available on host)
if command -v curl &>/dev/null; then
    success "curl found"
else
    warning "curl not found on host (non-critical, needed inside containers only)"
fi

# Docker daemon running?
if command -v docker &>/dev/null && ! docker info &>/dev/null 2>&1; then
    error "Docker daemon is not running. Please start Docker Desktop."
    PREREQ_FAILED=1
fi

if [[ "$PREREQ_FAILED" -eq 1 ]]; then
    error "Please install the missing prerequisites and try again."
    exit 1
fi

# =============================================================================
# STEP 1: GENERATE .env FILE
# =============================================================================
header "Step 1: Environment configuration..."

if [[ -f "$ENV_FILE" ]]; then
    warning ".env already exists — skipping generation."
    info "To regenerate, delete .env and re-run this script."
else
    if [[ ! -f "$ENV_EXAMPLE" ]]; then
        error ".env.example not found at $ENV_EXAMPLE"
        exit 1
    fi

    cp "$ENV_EXAMPLE" "$ENV_FILE"
    success "Copied .env.example → .env"

    # Auto-generate secure random keys using Python
    if command -v python3 &>/dev/null; then
        info "Generating secure random keys..."

        # Generate SECRET_KEY (JWT signing)
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null || echo "")
        if [[ -n "$SECRET_KEY" ]]; then
            if [[ "$(uname -s 2>/dev/null)" == "Darwin" ]]; then
                # macOS sed requires empty string after -i
                sed -i '' "s|your-super-secret-key-min-32-chars-change-this|$SECRET_KEY|g" "$ENV_FILE"
            else
                sed -i "s|your-super-secret-key-min-32-chars-change-this|$SECRET_KEY|g" "$ENV_FILE"
            fi
            success "Generated SECRET_KEY"
        fi

        # Generate FERNET_KEY (for encrypting GitHub tokens at rest)
        FERNET_KEY=$(python3 -c "
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except ImportError:
    import base64, os
    print(base64.urlsafe_b64encode(os.urandom(32)).decode())
" 2>/dev/null || echo "")
        if [[ -n "$FERNET_KEY" ]]; then
            if [[ "$(uname -s 2>/dev/null)" == "Darwin" ]]; then
                sed -i '' "s|^FERNET_KEY=$|FERNET_KEY=$FERNET_KEY|" "$ENV_FILE"
            else
                sed -i "s|^FERNET_KEY=$|FERNET_KEY=$FERNET_KEY|" "$ENV_FILE"
            fi
            success "Generated FERNET_KEY"
        fi

        # Generate GITHUB_WEBHOOK_SECRET
        WEBHOOK_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "")
        if [[ -n "$WEBHOOK_SECRET" ]]; then
            if [[ "$(uname -s 2>/dev/null)" == "Darwin" ]]; then
                sed -i '' "s|^GITHUB_WEBHOOK_SECRET=$|GITHUB_WEBHOOK_SECRET=$WEBHOOK_SECRET|" "$ENV_FILE"
            else
                sed -i "s|^GITHUB_WEBHOOK_SECRET=$|GITHUB_WEBHOOK_SECRET=$WEBHOOK_SECRET|" "$ENV_FILE"
            fi
            success "Generated GITHUB_WEBHOOK_SECRET"
        fi

        success "Secure keys auto-generated and written to .env"
    else
        warning "Python3 not available — please manually set SECRET_KEY, FERNET_KEY, GITHUB_WEBHOOK_SECRET in .env"
    fi

    echo ""
    echo -e "${YELLOW}${BOLD}  ACTION REQUIRED:${NC}"
    echo -e "  Please edit ${BOLD}.env${NC} and set:"
    echo -e "    ${BOLD}GITHUB_TOKEN${NC}      — Fine-grained PAT from https://github.com/settings/tokens"
    echo -e "    ${BOLD}GEMINI_API_KEY${NC}    — Free key from https://ai.google.dev"
    echo -e "    ${BOLD}GITHUB_USERNAME${NC}   — Your GitHub username"
    echo ""
    read -r -p "  Have you edited .env? (y/N): " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        warning "You can continue setup now and edit .env later."
        warning "The system will run in degraded mode until GITHUB_TOKEN is set."
    fi
fi

# =============================================================================
# STEP 2: BUILD DOCKER IMAGES
# =============================================================================
header "Step 2: Building Docker images (this may take 5-10 minutes)..."

cd "$PROJECT_ROOT"
$DOCKER_COMPOSE build --parallel
success "All Docker images built successfully"

# =============================================================================
# STEP 3: START INFRASTRUCTURE SERVICES
# =============================================================================
header "Step 3: Starting infrastructure services (postgres, redis, chromadb)..."

$DOCKER_COMPOSE up -d postgres redis chromadb
info "Waiting for databases to be healthy..."

# Wait for postgres
echo -n "  Waiting for PostgreSQL"
MAX_WAIT=60
WAITED=0
while ! $DOCKER_COMPOSE exec -T postgres pg_isready -U ose_user -d ose_db &>/dev/null 2>&1; do
    echo -n "."
    sleep 2
    WAITED=$((WAITED + 2))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        echo ""
        error "PostgreSQL failed to become healthy after ${MAX_WAIT}s"
        error "Check logs: $DOCKER_COMPOSE logs postgres"
        exit 1
    fi
done
echo ""
success "PostgreSQL is ready"

# Wait for Redis
echo -n "  Waiting for Redis"
WAITED=0
while ! $DOCKER_COMPOSE exec -T redis redis-cli ping &>/dev/null 2>&1; do
    echo -n "."
    sleep 2
    WAITED=$((WAITED + 2))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        echo ""
        error "Redis failed to become healthy after ${MAX_WAIT}s"
        exit 1
    fi
done
echo ""
success "Redis is ready"

# Wait for ChromaDB
echo -n "  Waiting for ChromaDB"
WAITED=0
while ! curl -sf http://localhost:8001/api/v1/heartbeat &>/dev/null 2>&1; do
    echo -n "."
    sleep 3
    WAITED=$((WAITED + 3))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        echo ""
        warning "ChromaDB may not be ready yet — continuing anyway"
        break
    fi
done
echo ""
success "ChromaDB is ready"

# =============================================================================
# STEP 4: RUN DATABASE MIGRATIONS
# =============================================================================
header "Step 4: Running database migrations..."

$DOCKER_COMPOSE run --rm backend alembic upgrade head
success "Database schema created (alembic upgrade head)"

# =============================================================================
# STEP 5: SEED INITIAL DATA
# =============================================================================
header "Step 5: Seeding initial data (GSoC orgs, CNCF projects)..."

$DOCKER_COMPOSE run --rm backend python scripts/seed.py
success "Initial data seeded (100+ OSS organizations loaded)"

# =============================================================================
# STEP 6: START ALL SERVICES
# =============================================================================
header "Step 6: Starting all services..."

$DOCKER_COMPOSE up -d
info "Waiting for backend to be ready..."

echo -n "  Waiting for backend API"
WAITED=0
MAX_WAIT=90
while ! curl -sf http://localhost:8000/health &>/dev/null 2>&1; do
    echo -n "."
    sleep 3
    WAITED=$((WAITED + 3))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        echo ""
        warning "Backend is still starting — it may take a bit longer"
        break
    fi
done
echo ""
success "All services started"

# =============================================================================
# STEP 7: STATUS SUMMARY
# =============================================================================
header "Setup Complete! 🎉"
echo ""
echo -e "${BOLD}Service Status:${NC}"
$DOCKER_COMPOSE ps
echo ""
echo -e "${BOLD}${GREEN}✅ OpenSource AI Engineer is running!${NC}"
echo ""
echo -e "  📊 ${BOLD}Dashboard:${NC}   http://localhost:3000"
echo -e "  🔌 ${BOLD}API:${NC}         http://localhost:8000"
echo -e "  📖 ${BOLD}API Docs:${NC}    http://localhost:8000/docs"
echo -e "  🗄️  ${BOLD}ChromaDB:${NC}   http://localhost:8001"
echo ""
echo -e "${BOLD}Next Steps:${NC}"
echo "  1. Ensure .env has GITHUB_TOKEN and GEMINI_API_KEY set"
echo "  2. If you updated .env, restart:  $DOCKER_COMPOSE restart"
echo "  3. Open http://localhost:3000 and watch the discovery agent find repos!"
echo "  4. View live logs:  $DOCKER_COMPOSE logs -f worker"
echo "  5. Stop everything: $DOCKER_COMPOSE down"
echo ""
echo -e "${BOLD}Useful Commands:${NC}"
echo "  View all logs:     $DOCKER_COMPOSE logs -f"
echo "  Restart backend:   $DOCKER_COMPOSE restart backend worker"
echo "  Stop all:          $DOCKER_COMPOSE down"
echo "  Destroy data:      $DOCKER_COMPOSE down -v  (⚠️  deletes all data)"
echo "  Shell into API:    $DOCKER_COMPOSE exec backend bash"
echo ""
