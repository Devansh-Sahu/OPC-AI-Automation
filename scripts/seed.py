#!/usr/bin/env python3
"""
=============================================================================
OpenSource AI Engineer — Database Seed Script
=============================================================================
Seeds the database with initial data so the system starts working immediately:

  1. GSoC 2024/2025 organizations (100+ GitHub orgs)
  2. CNCF graduated/incubating projects
  3. Apache Software Foundation projects
  4. Linux Foundation notable projects
  5. Default admin user (if AUTH_ENABLED)

Run with:
    python scripts/seed.py
    # or via Docker:
    docker-compose run --rm backend python scripts/seed.py
=============================================================================
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Setup path so we can import backend modules
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed")

# ---------------------------------------------------------------------------
# Known OSS Organization Seeds
# Format: (github_org, display_name, category, foundation)
# ---------------------------------------------------------------------------

GSOC_ORGS = [
    # Kubernetes ecosystem
    ("kubernetes",          "Kubernetes",               "container-orchestration", "cncf"),
    ("kubernetes-sigs",     "Kubernetes SIGs",          "container-orchestration", "cncf"),
    ("helm",                "Helm",                     "package-management",      "cncf"),
    ("etcd-io",             "etcd",                     "distributed-systems",     "cncf"),
    ("containerd",          "containerd",               "container-runtime",       "cncf"),
    # Observability
    ("prometheus",          "Prometheus",               "monitoring",              "cncf"),
    ("grafana",             "Grafana",                  "observability",           "cncf"),
    ("open-telemetry",      "OpenTelemetry",            "observability",           "cncf"),
    ("jaegertracing",       "Jaeger",                   "distributed-tracing",     "cncf"),
    ("thanos-io",           "Thanos",                   "monitoring",              "cncf"),
    ("victoriametrics",     "VictoriaMetrics",          "monitoring",              "independent"),
    # Service mesh & networking
    ("linkerd",             "Linkerd",                  "service-mesh",            "cncf"),
    ("envoyproxy",          "Envoy Proxy",              "networking",              "cncf"),
    ("cilium",              "Cilium",                   "networking",              "cncf"),
    ("coredns",             "CoreDNS",                  "networking",              "cncf"),
    ("istio",               "Istio",                    "service-mesh",            "cncf"),
    # GitOps / CI/CD
    ("argoproj",            "Argo Project",             "gitops",                  "cncf"),
    ("fluxcd",              "Flux",                     "gitops",                  "cncf"),
    ("tektoncd",            "Tekton",                   "ci-cd",                   "cncf"),
    ("spinnaker",           "Spinnaker",                "ci-cd",                   "cdf"),
    # Storage & databases
    ("rook-io",             "Rook",                     "storage",                 "cncf"),
    ("vitessio",            "Vitess",                   "database",                "cncf"),
    ("tikv",                "TiKV",                     "database",                "cncf"),
    ("longhorn-io",         "Longhorn",                 "storage",                 "cncf"),
    # Security
    ("falcosecurity",       "Falco",                    "security",                "cncf"),
    ("open-policy-agent",   "Open Policy Agent",        "security",                "cncf"),
    ("notaryproject",       "Notary",                   "security",                "cncf"),
    # Serverless / FaaS
    ("knative",             "Knative",                  "serverless",              "cncf"),
    ("openfaas",            "OpenFaaS",                 "serverless",              "independent"),
    ("kubeless",            "Kubeless",                 "serverless",              "cncf"),
    # ML / AI frameworks (popular GSoC targets)
    ("pytorch",             "PyTorch",                  "machine-learning",        "linux-foundation"),
    ("tensorflow",          "TensorFlow",               "machine-learning",        "google"),
    ("apache",              "Apache Software Foundation","big-data",               "apache"),
    ("huggingface",         "Hugging Face",             "machine-learning",        "independent"),
    ("ray-project",         "Ray",                      "distributed-computing",   "independent"),
    ("mlflow",              "MLflow",                   "mlops",                   "linux-foundation"),
    ("dmlc",                "XGBoost / MXNet",          "machine-learning",        "apache"),
    ("scikit-learn",        "scikit-learn",             "machine-learning",        "independent"),
    # Scientific Python
    ("numpy",               "NumPy",                    "scientific-computing",    "independent"),
    ("scipy",               "SciPy",                    "scientific-computing",    "independent"),
    ("matplotlib",          "Matplotlib",               "data-visualization",      "independent"),
    ("pandas-dev",          "pandas",                   "data-analysis",           "numfocus"),
    ("sympy",               "SymPy",                    "computer-algebra",        "numfocus"),
    ("jupyter",             "Jupyter",                  "interactive-computing",   "numfocus"),
    ("astropy",             "Astropy",                  "astronomy",               "numfocus"),
    ("networkx",            "NetworkX",                 "graph-theory",            "independent"),
    # Web frameworks
    ("django",              "Django",                   "web-framework",           "dsf"),
    ("pallets",             "Flask / Pallets",          "web-framework",           "independent"),
    ("encode",              "Starlette / HTTPx",        "web-framework",           "independent"),
    ("tiangolo",            "FastAPI",                  "web-framework",           "independent"),
    ("nodejs",              "Node.js",                  "runtime",                 "openjsf"),
    ("expressjs",           "Express.js",               "web-framework",           "openjsf"),
    # Databases & storage
    ("cockroachdb",         "CockroachDB",              "database",                "independent"),
    ("mongodb",             "MongoDB",                  "database",                "independent"),
    ("elastic",             "Elasticsearch",            "search",                  "independent"),
    ("opensearch-project",  "OpenSearch",               "search",                  "apache"),
    ("redis",               "Redis",                    "cache",                   "independent"),
    ("apache-cassandra",    "Apache Cassandra",         "database",                "apache"),
    ("prestodb",            "Presto",                   "query-engine",            "linux-foundation"),
    ("trinodb",             "Trino",                    "query-engine",            "independent"),
    # Apache projects
    ("apache",              "Apache (general)",         "various",                 "apache"),
    ("apache-airflow",      "Apache Airflow",           "workflow",                "apache"),
    ("apache-spark",        "Apache Spark",             "big-data",                "apache"),
    ("apache-kafka",        "Apache Kafka",             "streaming",               "apache"),
    ("apache-flink",        "Apache Flink",             "streaming",               "apache"),
    ("apache-beam",         "Apache Beam",              "batch-streaming",         "apache"),
    ("apache-arrow",        "Apache Arrow",             "data-format",             "apache"),
    ("apache-superset",     "Apache Superset",          "bi-dashboards",           "apache"),
    # DevOps tools
    ("hashicorp",           "HashiCorp",                "infrastructure",          "linux-foundation"),
    ("ansible",             "Ansible",                  "configuration-mgmt",      "red-hat"),
    ("saltstack",           "SaltStack",                "configuration-mgmt",      "independent"),
    ("puppet",              "Puppet",                   "configuration-mgmt",      "independent"),
    # Mozilla / Firefox
    ("mozilla",             "Mozilla",                  "browser",                 "mozilla-foundation"),
    ("mozilla-mobile",      "Mozilla Mobile",           "mobile",                  "mozilla-foundation"),
    # GNOME / KDE desktop
    ("GNOME",               "GNOME",                    "desktop",                 "gnome-foundation"),
    ("KDE",                 "KDE",                      "desktop",                 "kde-ev"),
    # Healthcare
    ("openmrs",             "OpenMRS",                  "healthcare",              "independent"),
    ("medplum",             "Medplum",                  "healthcare",              "independent"),
    # Education & community
    ("fossasia",            "FOSSASIA",                 "various",                 "fossasia"),
    ("sugarlabs",           "Sugar Labs",               "education",               "sfc"),
    ("publiclab",           "Public Lab",               "civic-tech",              "independent"),
    # Systems programming
    ("llvm",                "LLVM",                     "compiler",                "linux-foundation"),
    ("rust-lang",           "Rust Language",            "systems-programming",     "rust-foundation"),
    ("golang",              "Go Language",              "systems-programming",     "google"),
    ("WebAssembly",         "WebAssembly",              "runtime",                 "w3c"),
    ("bytecodealliance",    "Bytecode Alliance",        "wasm",                    "independent"),
    # Messaging & communication
    ("matrix-org",          "Matrix.org",               "messaging",               "matrix-foundation"),
    ("rocketchat",          "Rocket.Chat",              "messaging",               "independent"),
    ("mattermost",          "Mattermost",               "messaging",               "independent"),
    # CDN & web performance
    ("nicehash",            "NiceHash",                 "blockchain",              "independent"),
    ("cloudflare",          "Cloudflare",               "networking",              "independent"),
    # API tooling
    ("swagger-api",         "Swagger / OpenAPI",        "api-tooling",             "linux-foundation"),
    ("graphql",             "GraphQL",                  "api-query",               "graphql-foundation"),
    ("grpc",                "gRPC",                     "rpc-framework",           "cncf"),
    ("protocolbuffers",     "Protocol Buffers",         "serialization",           "google"),
    # Testing
    ("pytest-dev",          "pytest",                   "testing",                 "independent"),
    ("SeleniumHQ",          "Selenium",                 "testing",                 "sfc"),
    ("cypress-io",          "Cypress",                  "testing",                 "independent"),
    # Data formats & serialization
    ("msgpack",             "MessagePack",              "serialization",           "independent"),
    ("apache-parquet",      "Apache Parquet",           "data-format",             "apache"),
    ("dask",                "Dask",                     "distributed-computing",   "numfocus"),
    # Misc notable OSS
    ("caddyserver",         "Caddy",                    "web-server",              "independent"),
    ("traefik",             "Traefik",                  "reverse-proxy",           "independent"),
    ("nginx",               "NGINX",                    "web-server",              "f5"),
    ("curl",                "curl",                     "networking",              "independent"),
    ("git",                 "Git",                      "version-control",         "sfc"),
    ("git-lfs",             "Git LFS",                  "version-control",         "independent"),
    ("opencontainers",      "Open Containers Initiative","container-standards",    "linux-foundation"),
    ("open-cluster-management", "Open Cluster Management", "multi-cluster",       "cncf"),
    ("fluentd",             "Fluentd",                  "logging",                 "cncf"),
    ("fluent",              "Fluent Bit",               "logging",                 "cncf"),
    ("crossplane",          "Crossplane",               "infrastructure",          "cncf"),
    ("dapr",                "Dapr",                     "microservices",           "cncf"),
]

# ---------------------------------------------------------------------------
# Seed Logic
# ---------------------------------------------------------------------------

async def seed_repositories():
    """Insert seed organizations into the repositories_to_discover table."""
    log.info("Seeding %d OSS organizations...", len(GSOC_ORGS))

    # Try to import and use the actual database layer
    # If not available (e.g. running outside the app), fall back to direct SQL
    try:
        from backend.database import AsyncSessionLocal
        from backend.models.repository import Repository, RepositoryStatus
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            inserted = 0
            skipped = 0

            for github_org, display_name, category, foundation in GSOC_ORGS:
                # Check if already exists
                stmt = select(Repository).where(Repository.github_org == github_org)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    skipped += 1
                    continue

                repo = Repository(
                    github_org=github_org,
                    display_name=display_name,
                    category=category,
                    foundation=foundation,
                    status=RepositoryStatus.PENDING_DISCOVERY,
                    priority_score=0.5,
                    is_seed=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(repo)
                inserted += 1

            await session.commit()
            log.info("✅ Repositories: %d inserted, %d already existed", inserted, skipped)

    except ImportError as e:
        log.warning("Backend models not available (%s) — using raw SQL fallback", e)
        await seed_repositories_raw_sql()
    except Exception as e:
        log.warning("ORM seeding failed (%s) — trying raw SQL fallback", e)
        await seed_repositories_raw_sql()


async def seed_repositories_raw_sql():
    """Fallback: insert orgs using raw asyncpg/SQLAlchemy Core."""
    import asyncpg

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://ose_user:ose_password@localhost:5432/ose_db",
    )
    # asyncpg uses postgresql:// not postgresql+asyncpg://
    pg_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = await asyncpg.connect(pg_url)
    except Exception as e:
        log.error("Could not connect to database: %s", e)
        log.info("Skipping repository seeding (database not available yet)")
        return

    try:
        # Ensure the table exists (it may not if migrations haven't run)
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'repositories')"
        )

        if not table_exists:
            log.warning(
                "Table 'repositories' does not exist yet. "
                "Run alembic upgrade head first."
            )
            return

        inserted = 0
        skipped = 0

        for github_org, display_name, category, foundation in GSOC_ORGS:
            existing = await conn.fetchval(
                "SELECT id FROM repositories WHERE github_org = $1", github_org
            )
            if existing:
                skipped += 1
                continue

            await conn.execute(
                """
                INSERT INTO repositories
                    (github_org, display_name, category, foundation,
                     status, priority_score, is_seed, created_at, updated_at)
                VALUES
                    ($1, $2, $3, $4, 'pending_discovery', 0.5, true,
                     NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
                """,
                github_org, display_name, category, foundation,
            )
            inserted += 1

        log.info("✅ Repositories: %d inserted, %d already existed", inserted, skipped)
    finally:
        await conn.close()


async def seed_admin_user():
    """Create a default admin user if the users table exists and is empty."""
    import asyncpg
    from passlib.context import CryptContext

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://ose_user:ose_password@localhost:5432/ose_db",
    )
    pg_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = await asyncpg.connect(pg_url)
    except Exception as e:
        log.warning("Cannot connect to seed admin user: %s", e)
        return

    try:
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'users')"
        )
        if not table_exists:
            log.info("Users table not found — skipping admin user creation")
            return

        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        if user_count and user_count > 0:
            log.info("Users already exist (%d) — skipping admin creation", user_count)
            return

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin-change-me-now!")
        hashed = pwd_context.hash(default_password)

        await conn.execute(
            """
            INSERT INTO users (email, username, hashed_password, is_admin, is_active, created_at)
            VALUES ($1, $2, $3, true, true, NOW() AT TIME ZONE 'UTC')
            """,
            "admin@ose.local", "admin", hashed,
        )
        log.info("✅ Default admin user created: admin@ose.local / %s", default_password)
        log.warning("⚠️  CHANGE THE ADMIN PASSWORD immediately after first login!")
    except Exception as e:
        log.warning("Admin user seeding failed: %s", e)
    finally:
        await conn.close()


async def seed_discovery_config():
    """Seed default agent configuration settings."""
    import asyncpg

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://ose_user:ose_password@localhost:5432/ose_db",
    )
    pg_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = await asyncpg.connect(pg_url)
    except Exception as e:
        log.warning("Cannot connect to seed config: %s", e)
        return

    try:
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'agent_config')"
        )
        if not table_exists:
            log.info("agent_config table not found — skipping config seeding")
            return

        default_configs = [
            ("issue_discovery.min_stars", "100", "Minimum GitHub stars for issue discovery"),
            ("issue_discovery.max_age_days", "30", "Maximum age of issues to consider"),
            ("issue_discovery.complexity_labels",
             "['senior', 'staff', 'complex', 'architecture', 'refactor', 'performance', 'security']",
             "Labels indicating senior-level issues"),
            ("repo_discovery.min_stars", "500", "Minimum stars for a repo to be tracked"),
            ("repo_discovery.languages",
             "['Python', 'Go', 'Rust', 'TypeScript', 'Java', 'C++']",
             "Target programming languages"),
            ("pr.draft_only", "true", "Only create draft PRs"),
            ("pr.max_file_changes", "20", "Maximum files changed per PR"),
        ]

        for key, value, description in default_configs:
            existing = await conn.fetchval(
                "SELECT id FROM agent_config WHERE key = $1", key
            )
            if not existing:
                await conn.execute(
                    "INSERT INTO agent_config (key, value, description, created_at) "
                    "VALUES ($1, $2, $3, NOW() AT TIME ZONE 'UTC')",
                    key, value, description,
                )

        log.info("✅ Default agent configuration seeded")
    except Exception as e:
        log.warning("Config seeding failed: %s", e)
    finally:
        await conn.close()


async def main():
    log.info("=" * 60)
    log.info("OpenSource AI Engineer — Database Seeder")
    log.info("=" * 60)
    log.info("Timestamp: %s", datetime.now(timezone.utc).isoformat())
    log.info("")

    # Run all seed operations
    log.info("📦 Seeding OSS organization list (%d orgs)...", len(GSOC_ORGS))
    await seed_repositories()

    log.info("👤 Seeding default admin user...")
    await seed_admin_user()

    log.info("⚙️  Seeding default agent configuration...")
    await seed_discovery_config()

    log.info("")
    log.info("=" * 60)
    log.info("✅ Seeding complete!")
    log.info("=" * 60)
    log.info("")
    log.info("The discovery agent will now scan these organizations")
    log.info("for senior-level issues automatically.")
    log.info("")
    log.info("Open the dashboard at http://localhost:3000 to get started.")


if __name__ == "__main__":
    asyncio.run(main())
