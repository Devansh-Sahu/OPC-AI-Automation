# 🤖 OpenSource AI Engineer

> An autonomous AI software engineering system that discovers world-class open-source repositories, analyzes complex technical issues, generates senior-engineer-level fixes, and creates draft PRs — all at ₹0/month.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Node.js 20](https://img.shields.io/badge/node-20.x-green.svg)](https://nodejs.org/en)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docs.docker.com/compose/)

---

## ✨ What Makes This Different

| Typical "AI Code Bot" | OpenSource AI Engineer |
|---|---|
| Fixes typos and "good first issues" | Targets **SENIOR/STAFF/INNOVATION** complexity |
| Requires pre-configured repos | **Autonomous repo discovery** (GSoC, CNCF, Apache) |
| Submits PRs without human review | **Draft PRs only** — you approve before anything goes public |
| Crashes and stays broken | **Self-healing** — if tests fail, the agent retries automatically |
| Prototype quality | **Production-grade** — sandboxed execution, circuit breakers, LangGraph checkpointing |
| Costs $100s/month | **₹0/month** (Gemini free tier + Ollama local) |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     OpenSource AI Engineer                          │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  Phase 0: Discovery                           │   │
│  │   Repo Discovery Agent  ──►  GitHub API / GSoC / CNCF        │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
│                                 │                                   │
│  ┌──────────────────────────────▼───────────────────────────────┐   │
│  │                  Phase 1: Issue Scoring                       │   │
│  │   Issue Discovery Agent  ──►  XGBoost Complexity Scorer      │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
│                                 │ (SENIOR / STAFF / INNOVATION)     │
│  ┌──────────────────────────────▼───────────────────────────────┐   │
│  │                  Phase 2: Code Intelligence                   │   │
│  │   Repository Analyzer (AST) + Code Retrieval (RAG/ChromaDB)  │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
│                                 │                                   │
│  ┌──────────────────────────────▼───────────────────────────────┐   │
│  │                  Phase 3: Engineering                         │   │
│  │   Planning Agent  ──►  Coding Agent  ──►  Testing Agent      │   │
│  │          │                    │                │             │   │
│  │    RFC-quality plan    Sandboxed codegen   Self-healing       │   │
│  │                               │                │             │   │
│  │                        Review Agent ◄──────────┘             │   │
│  │                   (security + perf analysis)                 │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
│                                 │                                   │
│  ┌──────────────────────────────▼───────────────────────────────┐   │
│  │                  Phase 4: PR & Notification                   │   │
│  │   PR Agent (DRAFT only)  ──►  Notification Agent             │   │
│  │                               (Telegram / Discord / Email)   │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
│                                 │                                   │
│  ┌──────────────────────────────▼───────────────────────────────┐   │
│  │                  ∞ Continuous Learning                        │   │
│  │   Learning Agent (XGBoost)  +  Innovation Agent (RFCs)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

Infrastructure:
  PostgreSQL 16 ── Redis 7 ── ChromaDB ── Docker Sandbox
  FastAPI Backend ── Next.js Dashboard ── LangGraph Orchestration
```

---

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** ([download](https://docs.docker.com/get-docker/))
- **GitHub Personal Access Token** (fine-grained PAT)
- **Gemini API Key** — free at [ai.google.dev](https://ai.google.dev) (1M tokens/day)

> **Prefer 100% local?** Skip Gemini — use Ollama instead. See [Using Ollama](#using-ollama-no-api-keys).

### One-Command Setup

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/opensource-ai-engineer
cd opensource-ai-engineer

# 2. Make setup script executable
chmod +x scripts/setup.sh

# 3. Run one-command setup
./scripts/setup.sh
```

The setup script automatically:
- ✅ Checks Docker and prerequisites
- ✅ Generates `.env` with cryptographically secure keys
- ✅ Builds all Docker images
- ✅ Starts PostgreSQL, Redis, ChromaDB
- ✅ Runs database migrations (`alembic upgrade head`)
- ✅ Seeds 100+ OSS organizations (GSoC, CNCF, Apache)
- ✅ Starts all services

### 2. Configure Secrets

After setup, edit `.env`:

```env
# Required — get from https://github.com/settings/tokens
GITHUB_TOKEN=ghp_your_token_here
GITHUB_USERNAME=your_github_username

# Required (or use Ollama) — free at https://ai.google.dev
GEMINI_API_KEY=AIza_your_key_here

# Optional but recommended — get from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=123456789:your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Then restart:
```bash
docker-compose restart
```

### 3. Open the Dashboard

```
📊 Dashboard:  http://localhost:3000
🔌 API:        http://localhost:8000
📖 API Docs:   http://localhost:8000/docs
```

---

## 🧩 Using Ollama (No API Keys)

Run entirely locally with no external API costs:

```bash
# 1. Install Ollama
# Linux/Mac:
curl https://ollama.ai/install.sh | sh
# Windows: download from https://ollama.ai/download

# 2. Pull a capable coding model (pick one)
ollama pull qwen3:14b          # Best quality (14B params, ~9GB)
ollama pull deepseek-coder:6.7b # Great for code specifically (~4GB)
ollama pull llama3.1:8b         # Fast and capable (~5GB)

# 3. Configure .env
GEMINI_API_KEY=                              # Leave empty
OLLAMA_BASE_URL=http://host.docker.internal:11434  # Reaches host from Docker
OLLAMA_MODEL=qwen3:14b
```

---

## 🤖 Agent Pipeline

| Phase | Agent | Complexity | Description |
|---|---|---|---|
| 0 | **Repo Discovery** | Low | Autonomously scans GSoC, CNCF, Apache, Linux Foundation GitHub orgs |
| 1 | **Issue Discovery** | Medium | Finds SENIOR/STAFF/INNOVATION complexity issues using XGBoost scoring |
| 2 | **Repository Analyzer** | High | Deep AST analysis, architecture detection, tech stack identification |
| 2 | **Code Retrieval** | Medium | RAG with AST-aware chunking stored in ChromaDB |
| 3 | **Planning** | High | Generates RFC-quality engineering plans with trade-off analysis |
| 3 | **Coding** | High | Sandboxed code generation with full context from RAG |
| 3 | **Testing** | Medium | Auto-detects test framework, runs tests, self-heals on failure |
| 3 | **Review** | High | AI security audit + performance analysis |
| 4 | **PR Agent** | Low | Creates **DRAFT** PR only — never auto-merges |
| 4 | **Notification** | Low | Sends Telegram/Discord/Email alerts with PR link |
| ∞ | **Learning** | Medium | Retrains XGBoost from merged/rejected PR outcomes |
| ∞ | **Innovation** | High | Proactively generates RFC proposals for improvements |

### Issue Complexity Classification

The system only works on issues classified as:

| Level | Description | Example |
|---|---|---|
| `SENIOR` | Significant architecture or performance work | "Optimize query planner for 10x speedup" |
| `STAFF` | Cross-cutting technical leadership | "Design new plugin architecture" |
| `INNOVATION` | Novel features or research-level improvements | "Implement adaptive sampling algorithm" |

It deliberately **ignores** `good-first-issue`, documentation typos, and simple bug fixes.

---

## 💰 Cost Analysis

| Component | Provider | Cost |
|---|---|---|
| LLM inference | Gemini 2.5 Flash | **Free** (1M tokens/day) |
| LLM inference (alternative) | Ollama (local) | **Free** |
| Vector database | ChromaDB (self-hosted) | **Free** |
| Relational database | PostgreSQL (self-hosted) | **Free** |
| Cache / queue | Redis (self-hosted) | **Free** |
| Code execution | Docker sandbox (local) | **Free** |
| **Total** | | **₹0 / month** |

---

## 🔒 Security

### Defense in Depth

1. **Sandboxed Execution** — AI-generated code runs in isolated Docker containers with:
   - `--network=none` (no internet access)
   - `--read-only` filesystem (only `/workspace` is writable)
   - `--memory=512m --cpus=1 --pids-limit=128` (resource limits)
   - `--security-opt=no-new-privileges` (no privilege escalation)
   - Automatic timeout and kill after `SANDBOX_TIMEOUT_SECONDS`

2. **Token Encryption** — GitHub tokens are encrypted at rest using Fernet symmetric encryption before storage in PostgreSQL

3. **Draft PRs Only** — The system can NEVER auto-merge or push to main branches. Every PR requires human approval.

4. **Circuit Breakers** — Prevent runaway API costs; agents back off automatically on rate limiting

5. **Audit Logging** — Every agent action is logged with timestamp, inputs, outputs, and agent ID

6. **Webhook Verification** — GitHub webhooks verified using HMAC-SHA256 with `GITHUB_WEBHOOK_SECRET`

---

## 📊 Dashboard Pages

| Page | Description |
|---|---|
| **Dashboard** | KPIs overview, live agent status, recent activity feed |
| **Discover** | Browse auto-discovered repositories sorted by opportunity score |
| **Repositories** | All tracked repositories with tech stack analysis |
| **Issues** | Senior-level issues ranked by complexity and impact score |
| **Agent Runs** | Live WebSocket view of agent progress (step-by-step) |
| **Pull Requests** | Review and approve/reject draft PRs |
| **Innovation** | RFC proposals and proactive improvement backlog |
| **Analytics** | Merge rates, success metrics, token usage, time-to-PR |
| **Settings** | LLM provider, GitHub, notifications configuration |

---

## 🛠️ Local Development

### Backend (FastAPI)

```bash
# Create virtual environment
python -m venv .venv

# Activate (Linux/Mac)
source .venv/bin/activate

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your secrets

# Run migrations
alembic upgrade head

# Seed data
python scripts/seed.py

# Start development server (with auto-reload)
uvicorn backend.main:app --reload --port 8000
```

### Frontend (Next.js)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
# Dashboard available at http://localhost:3000
```

### Running Tests

```bash
# Backend tests
pytest backend/tests/ -v --cov=backend

# Frontend tests
cd frontend && npm test
```

---

## 📁 Project Structure

```
opensource-ai-engineer/
├── docker-compose.yml          # All services orchestration
├── docker/
│   ├── backend.Dockerfile      # Python/FastAPI multi-stage build
│   ├── frontend.Dockerfile     # Next.js multi-stage build
│   └── sandbox.Dockerfile      # Isolated code execution environment
├── .env.example                # All environment variables documented
├── .gitignore                  # Comprehensive ignore rules
├── scripts/
│   ├── setup.sh                # One-command setup script
│   └── seed.py                 # Database seeder (100+ OSS orgs)
├── backend/
│   ├── main.py                 # FastAPI app entrypoint
│   ├── agents/                 # All 12 LangGraph agent implementations
│   │   ├── discovery/          # Repo + issue discovery agents
│   │   ├── analysis/           # Repository analyzer + code retrieval
│   │   ├── engineering/        # Planning + coding + testing + review
│   │   ├── pr/                 # PR creation + notification agents
│   │   └── learning/           # XGBoost learning + innovation agents
│   ├── api/                    # FastAPI routers
│   ├── models/                 # SQLAlchemy models
│   ├── workers/                # Background job scheduler
│   ├── sandbox/                # Docker sandbox orchestration
│   └── database.py             # Async database configuration
├── alembic/                    # Database migrations
│   └── versions/               # Migration files
├── frontend/                   # Next.js 14 dashboard
│   ├── app/                    # App Router pages
│   ├── components/             # React components
│   └── lib/                    # API client, utilities
└── requirements.txt            # Python dependencies
```

---

## 📖 Configuration Reference

All configuration is done via environment variables. See [`.env.example`](.env.example) for the full reference with descriptions.

### Key Variables

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | ✅ Yes | Fine-grained PAT for PR creation |
| `GITHUB_USERNAME` | ✅ Yes | Your GitHub username |
| `GEMINI_API_KEY` | ⚡ Recommended | Free LLM (or use Ollama) |
| `OLLAMA_BASE_URL` | 🔄 Alternative | Local Ollama endpoint |
| `SECRET_KEY` | ✅ Yes | JWT signing key (auto-generated) |
| `FERNET_KEY` | ✅ Yes | Token encryption key (auto-generated) |
| `TELEGRAM_BOT_TOKEN` | ❌ Optional | PR notifications |
| `DISCORD_WEBHOOK_URL` | ❌ Optional | Discord notifications |
| `ENABLE_SANDBOX` | ❌ Optional | Disable if Docker-in-Docker unavailable |
| `DRAFT_PRS_ONLY` | ✅ Recommended | Keep `true` for safety |

---

## 🔧 Useful Commands

```bash
# Start all services
docker-compose up -d

# View live logs (all services)
docker-compose logs -f

# View worker/agent logs only
docker-compose logs -f worker

# Restart after .env changes
docker-compose restart

# Run database migrations manually
docker-compose run --rm backend alembic upgrade head

# Shell into backend container
docker-compose exec backend bash

# Shell into worker container
docker-compose exec worker bash

# Stop all services (keep data)
docker-compose down

# Stop and DELETE all data (full reset)
docker-compose down -v

# Rebuild images after code changes
docker-compose build --no-cache

# Check service health
docker-compose ps
```

---

## 🤝 Contributing

This project itself was designed and built with AI assistance. Contributions are very welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-improvement`
3. Make your changes with tests
4. Push: `git push origin feature/amazing-improvement`
5. Open a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 🗺️ Roadmap

- [x] Core 12-agent LangGraph pipeline
- [x] Autonomous repository discovery (GSoC/CNCF/Apache)
- [x] Docker sandbox for safe code execution
- [x] Next.js dashboard with WebSocket live updates
- [x] Telegram/Discord/Email notifications
- [x] XGBoost issue complexity scoring
- [ ] GitHub App support (higher rate limits)
- [ ] Multi-language support (Java, C++, Rust)
- [ ] Automatic issue comment (before PR creation)
- [ ] Fine-tuned model for OSS code review
- [ ] Cloud deployment guide (AWS/GCP/Fly.io)
- [ ] PR analytics and merge rate dashboard

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

Built on the shoulders of giants:
- [LangGraph](https://github.com/langchain-ai/langgraph) — Agent orchestration
- [FastAPI](https://fastapi.tiangolo.com/) — Backend framework
- [ChromaDB](https://www.trychroma.com/) — Vector store
- [Gemini](https://ai.google.dev) — Free LLM tier
- [Ollama](https://ollama.ai) — Local LLM inference
- All the incredible open-source communities whose projects this system helps improve

---

<div align="center">
  <strong>⭐ If this project helps you contribute to open source, please star it! ⭐</strong>
  <br/><br/>
  Built with ❤️ for the open-source community
</div>
