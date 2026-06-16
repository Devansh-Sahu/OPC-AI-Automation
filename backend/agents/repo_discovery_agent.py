"""
Repo Discovery Agent - Fully autonomous repository discovery from multiple sources.
No manual input required. Crawls GSoC, CNCF, Apache, LF, GitHub Trending, and more.
"""

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, TypedDict
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent, BaseAgentState
from backend.core.config import settings
from backend.core.circuit_breaker import circuit_breaker
from backend.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── Known GSoC organizations (augmented from API) ──────────────────────────
KNOWN_GSOC_ORGS = [
    "python", "django", "flask", "numpy", "scipy", "pandas",
    "matplotlib", "scikit-learn", "tensorflow", "pytorch",
    "apache", "linux", "kde", "gnome", "mozilla", "wikimedia",
    "cncf", "kubernetes", "prometheus", "grafana", "envoy",
    "opentelemetry", "fluentd", "jaeger", "vitess", "argo",
    "rust-lang", "golang", "julia", "haskell", "ocaml",
    "postgresql", "mysql", "redis", "elasticsearch", "mongodb",
    "sympy", "sagemath", "astropy", "sunpy", "biopython",
    "openmrs", "ushahidi", "mifos", "openstreetmap",
    "boost", "llvm", "gcc", "gdb", "binutils",
]

LINUX_FOUNDATION_ORGS = [
    "kubernetes", "cncf", "linux", "torvalds", "hyperledger",
    "opendaylight", "onap", "lf-edge", "iovisor", "falcosecurity",
    "thanos-io", "cortexproject", "m3db", "OpenObservability",
    "open-policy-agent", "spiffe", "telepresenceio",
    "networkservicemesh", "nats-io", "tikv",
]

CNCF_GITHUB_ORGS = [
    "kubernetes", "prometheus", "envoyproxy", "containerd",
    "coredns", "fluentd", "jaegertracing", "linkerd", "argo-cd",
    "open-telemetry", "thanos-io", "cortexproject", "vitessio",
    "fluxcd", "crossplane", "cert-manager", "kubeedge",
    "chaos-mesh", "cubeFS", "emissary-ingress", "skooner-k8dash",
    "backstage-io", "dapr", "keda-sh", "openkruise",
]


class RepoDiscoveryState(BaseAgentState):
    sources_crawled: List[str]
    raw_repos: List[Dict[str, Any]]
    scored_repos: List[Dict[str, Any]]
    upserted_count: int
    skipped_count: int


class RepoDiscoveryAgent(BaseAgent):
    """
    Autonomously discovers open-source repositories from multiple authoritative sources,
    scores them on a composite quality metric, and upserts them into the repositories table.
    """

    def __init__(self):
        super().__init__("repo_discovery_agent")
        self.github_headers = {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.session: Optional[aiohttp.ClientSession] = None

    # ── Graph construction ──────────────────────────────────────────────────

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(RepoDiscoveryState)

        graph.add_node("init_session", self._node_init_session)
        graph.add_node("crawl_gsoc", self._node_crawl_gsoc)
        graph.add_node("crawl_cncf", self._node_crawl_cncf)
        graph.add_node("crawl_apache", self._node_crawl_apache)
        graph.add_node("crawl_github_trending", self._node_crawl_github_trending)
        graph.add_node("crawl_github_search", self._node_crawl_github_search)
        graph.add_node("crawl_awesome_lists", self._node_crawl_awesome_lists)
        graph.add_node("fetch_github_metadata", self._node_fetch_github_metadata)
        graph.add_node("score_repos", self._node_score_repos)
        graph.add_node("upsert_to_db", self._node_upsert_to_db)
        graph.add_node("finalize", self._node_finalize)

        graph.set_entry_point("init_session")
        graph.add_edge("init_session", "crawl_gsoc")
        graph.add_edge("crawl_gsoc", "crawl_cncf")
        graph.add_edge("crawl_cncf", "crawl_apache")
        graph.add_edge("crawl_apache", "crawl_github_trending")
        graph.add_edge("crawl_github_trending", "crawl_github_search")
        graph.add_edge("crawl_github_search", "crawl_awesome_lists")
        graph.add_edge("crawl_awesome_lists", "fetch_github_metadata")
        graph.add_edge("fetch_github_metadata", "score_repos")
        graph.add_edge("score_repos", "upsert_to_db")
        graph.add_edge("upsert_to_db", "finalize")
        graph.add_edge("finalize", END)

        return graph

    async def run(
        self, input_data: Optional[Dict[str, Any]] = None, run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute repo discovery pipeline."""
        if not self._initialized:
            await self.initialize()

        run_id = run_id or self._new_run_id()
        ctx = self._create_context(run_id)

        initial_state: RepoDiscoveryState = {
            **self._base_initial_state(run_id),
            "sources_crawled": [],
            "raw_repos": [],
            "scored_repos": [],
            "upserted_count": 0,
            "skipped_count": 0,
        }

        config = {"configurable": {"thread_id": run_id}}

        try:
            final_state = await self.compiled_graph.ainvoke(initial_state, config=config)
            ctx.record_step("complete")
            return final_state
        except Exception as e:
            ctx.record_error(str(e))
            logger.error(f"Repo discovery failed: {e}", exc_info=True)
            raise

    # ── Node implementations ────────────────────────────────────────────────

    async def _node_init_session(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Initialize aiohttp session."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "OpenSourceAIEngineer/1.0"},
        )
        return {"current_step": "init_session"}

    async def _node_crawl_gsoc(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Crawl GSoC organizations and map to GitHub repos."""
        repos = list(state["raw_repos"])
        sources = list(state["sources_crawled"])

        gsoc_repos = []
        try:
            # Try GSoC API first
            async with self.session.get(
                "https://summerofcode.withgoogle.com/api/organizations/?status=1",
                headers={"Accept": "application/json"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    orgs = data if isinstance(data, list) else data.get("results", [])
                    for org in orgs[:50]:
                        github_url = org.get("github_url", "") or org.get("url", "")
                        if "github.com" in github_url:
                            owner = github_url.rstrip("/").split("/")[-1]
                            org_repos = await self._get_org_top_repos(owner, gsoc_bonus=True)
                            gsoc_repos.extend(org_repos)
        except Exception as e:
            logger.warning(f"GSoC API unavailable, using known org list: {e}")

        # Always also search from known list
        for org in KNOWN_GSOC_ORGS[:20]:
            org_repos = await self._get_org_top_repos(org, gsoc_bonus=True)
            gsoc_repos.extend(org_repos)

        repos.extend(gsoc_repos)
        sources.append("gsoc")
        logger.info(f"GSoC crawl: found {len(gsoc_repos)} repos")
        return {"raw_repos": repos, "sources_crawled": sources, "current_step": "crawl_gsoc"}

    async def _node_crawl_cncf(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Crawl CNCF landscape and GitHub orgs."""
        repos = list(state["raw_repos"])
        sources = list(state["sources_crawled"])
        cncf_repos = []

        for org in CNCF_GITHUB_ORGS:
            org_repos = await self._get_org_top_repos(org, gsoc_bonus=False)
            cncf_repos.extend(org_repos)
            await asyncio.sleep(0.5)

        repos.extend(cncf_repos)
        sources.append("cncf")
        logger.info(f"CNCF crawl: found {len(cncf_repos)} repos")
        return {"raw_repos": repos, "sources_crawled": sources, "current_step": "crawl_cncf"}

    async def _node_crawl_apache(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Crawl Apache Software Foundation projects."""
        repos = list(state["raw_repos"])
        sources = list(state["sources_crawled"])
        apache_repos = []

        try:
            async with self.session.get(
                "https://projects.apache.org/json/projects-by-pmc.json"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    for pmc, projects in list(data.items())[:30]:
                        for project_name in (projects if isinstance(projects, list) else [projects])[:3]:
                            # Apache repos are at github.com/apache/{name}
                            apache_repos.append({
                                "full_name": f"apache/{project_name}",
                                "owner": "apache",
                                "name": project_name,
                                "is_gsoc_org": False,
                                "source": "apache",
                            })
        except Exception as e:
            logger.warning(f"Apache projects API failed: {e}")
            # Fallback: search Apache org
            org_repos = await self._get_org_top_repos("apache", gsoc_bonus=False)
            apache_repos.extend(org_repos)

        repos.extend(apache_repos)
        sources.append("apache")
        logger.info(f"Apache crawl: found {len(apache_repos)} repos")
        return {"raw_repos": repos, "sources_crawled": sources, "current_step": "crawl_apache"}

    async def _node_crawl_github_trending(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Parse GitHub Trending page for hot repos."""
        repos = list(state["raw_repos"])
        sources = list(state["sources_crawled"])
        trending_repos = []

        for language in ["python", "javascript", "typescript", "go", "rust", ""]:
            url = f"https://github.com/trending/{language}?since=weekly"
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        soup = BeautifulSoup(html, "html.parser")
                        articles = soup.select("article.Box-row")
                        for article in articles[:10]:
                            link = article.select_one("h2 a")
                            if link:
                                href = link.get("href", "").strip("/")
                                parts = href.split("/")
                                if len(parts) == 2:
                                    trending_repos.append({
                                        "full_name": href,
                                        "owner": parts[0],
                                        "name": parts[1],
                                        "is_gsoc_org": parts[0].lower() in KNOWN_GSOC_ORGS,
                                        "source": "github_trending",
                                    })
            except Exception as e:
                logger.warning(f"GitHub trending parse failed for {language}: {e}")
            await asyncio.sleep(1)

        repos.extend(trending_repos)
        sources.append("github_trending")
        logger.info(f"GitHub Trending: found {len(trending_repos)} repos")
        return {"raw_repos": repos, "sources_crawled": sources, "current_step": "crawl_github_trending"}

    async def _node_crawl_github_search(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Use GitHub Search API for high-quality repos."""
        repos = list(state["raw_repos"])
        sources = list(state["sources_crawled"])
        search_repos = []

        queries = [
            "language:python stars:>2000 pushed:>2024-01-01 is:public",
            "language:javascript stars:>2000 pushed:>2024-01-01 is:public",
            "language:typescript stars:>1500 pushed:>2024-01-01 is:public",
            "language:go stars:>1500 pushed:>2024-01-01 is:public",
            "language:rust stars:>1000 pushed:>2024-01-01 is:public",
            "language:java stars:>2000 pushed:>2024-01-01 is:public",
        ]

        for query in queries:
            try:
                async with self.session.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "sort": "stars", "per_page": 30},
                    headers=self.github_headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data.get("items", []):
                            owner = item["owner"]["login"]
                            search_repos.append({
                                "full_name": item["full_name"],
                                "owner": owner,
                                "name": item["name"],
                                "is_gsoc_org": owner.lower() in KNOWN_GSOC_ORGS,
                                "source": "github_search",
                                "stars": item.get("stargazers_count", 0),
                                "language": item.get("language", ""),
                                "description": item.get("description", ""),
                                "open_issues_count": item.get("open_issues_count", 0),
                                "forks_count": item.get("forks_count", 0),
                                "pushed_at": item.get("pushed_at", ""),
                                "html_url": item.get("html_url", ""),
                            })
                    elif resp.status == 403:
                        logger.warning("GitHub search rate limited, pausing 60s")
                        await asyncio.sleep(60)
            except Exception as e:
                logger.warning(f"GitHub search failed for query '{query[:50]}': {e}")
            await asyncio.sleep(2)

        repos.extend(search_repos)
        sources.append("github_search")
        logger.info(f"GitHub Search: found {len(search_repos)} repos")
        return {"raw_repos": repos, "sources_crawled": sources, "current_step": "crawl_github_search"}

    async def _node_crawl_awesome_lists(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Parse sindresorhus/awesome for high-quality repo links."""
        repos = list(state["raw_repos"])
        sources = list(state["sources_crawled"])
        awesome_repos = []

        try:
            async with self.session.get(
                "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md"
            ) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    # Extract GitHub repo links
                    pattern = r"https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)"
                    matches = re.findall(pattern, content)
                    seen = set()
                    for owner, name in matches[:100]:
                        full_name = f"{owner}/{name}"
                        if full_name not in seen and owner.lower() not in ["sindresorhus"]:
                            seen.add(full_name)
                            awesome_repos.append({
                                "full_name": full_name,
                                "owner": owner,
                                "name": name,
                                "is_gsoc_org": owner.lower() in KNOWN_GSOC_ORGS,
                                "source": "awesome_lists",
                            })
        except Exception as e:
            logger.warning(f"Awesome lists crawl failed: {e}")

        repos.extend(awesome_repos)
        sources.append("awesome_lists")
        logger.info(f"Awesome lists: found {len(awesome_repos)} repos")
        return {"raw_repos": repos, "sources_crawled": sources, "current_step": "crawl_awesome_lists"}

    async def _node_fetch_github_metadata(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Fetch full GitHub metadata for all discovered repos (deduplicated)."""
        raw_repos = state["raw_repos"]

        # Deduplicate by full_name
        seen = {}
        for repo in raw_repos:
            fn = repo.get("full_name", "")
            if fn and fn not in seen:
                seen[fn] = repo

        unique_repos = list(seen.values())
        logger.info(f"Fetching metadata for {len(unique_repos)} unique repos")

        enriched = []
        semaphore = asyncio.Semaphore(10)

        async def fetch_one(repo: Dict) -> Optional[Dict]:
            async with semaphore:
                # Skip if we already have full metadata from search
                if repo.get("stars") is not None and repo.get("pushed_at"):
                    return repo
                try:
                    async with self.session.get(
                        f"https://api.github.com/repos/{repo['full_name']}",
                        headers=self.github_headers,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return {
                                **repo,
                                "stars": data.get("stargazers_count", 0),
                                "forks_count": data.get("forks_count", 0),
                                "open_issues_count": data.get("open_issues_count", 0),
                                "language": data.get("language", ""),
                                "description": data.get("description", ""),
                                "pushed_at": data.get("pushed_at", ""),
                                "created_at": data.get("created_at", ""),
                                "html_url": data.get("html_url", ""),
                                "topics": data.get("topics", []),
                                "license": (data.get("license") or {}).get("spdx_id", ""),
                                "default_branch": data.get("default_branch", "main"),
                                "archived": data.get("archived", False),
                                "disabled": data.get("disabled", False),
                                "size_kb": data.get("size", 0),
                            }
                        elif resp.status == 404:
                            return None
                        elif resp.status == 403:
                            await asyncio.sleep(30)
                            return repo
                        return repo
                except Exception as e:
                    logger.debug(f"Metadata fetch failed for {repo.get('full_name')}: {e}")
                    return repo
                finally:
                    await asyncio.sleep(0.2)

        tasks = [fetch_one(r) for r in unique_repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if r and not isinstance(r, Exception) and not r.get("archived") and not r.get("disabled"):
                enriched.append(r)

        # Also fetch PR stats for top repos
        top_repos = sorted(enriched, key=lambda x: x.get("stars", 0), reverse=True)[:50]
        for repo in top_repos:
            pr_stats = await self._fetch_pr_stats(repo["full_name"])
            repo.update(pr_stats)

        logger.info(f"Enriched {len(enriched)} repos with metadata")
        return {"raw_repos": enriched, "current_step": "fetch_github_metadata"}

    async def _node_score_repos(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Score each repo using composite quality formula."""
        repos = state["raw_repos"]
        scored = []

        for repo in repos:
            score = self._compute_composite_score(repo)
            scored.append({**repo, "composite_quality_score": score})

        # Sort by score descending
        scored.sort(key=lambda x: x["composite_quality_score"], reverse=True)
        logger.info(f"Scored {len(scored)} repos. Top score: {scored[0]['composite_quality_score']:.2f}" if scored else "No repos to score")
        return {"scored_repos": scored, "current_step": "score_repos"}

    async def _node_upsert_to_db(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Upsert scored repos into the repositories table."""
        scored_repos = state["scored_repos"]
        upserted = 0
        skipped = 0

        async with AsyncSessionLocal() as session:
            from backend.models.repository import Repository
            from sqlalchemy import select

            cutoff = datetime.now(timezone.utc) - timedelta(days=7)

            for repo_data in scored_repos[:500]:  # Cap at top 500
                try:
                    full_name = repo_data.get("full_name", "")
                    if not full_name:
                        continue

                    # Check if recently discovered
                    result = await session.execute(
                        select(Repository).where(Repository.full_name == full_name)
                    )
                    existing = result.scalar_one_or_none()

                    new_score = repo_data.get("composite_quality_score", 0)

                    if existing:
                        # Skip if discovered recently and score hasn't changed significantly
                        if existing.last_discovered_at and existing.last_discovered_at > cutoff:
                            score_diff = abs((existing.composite_quality_score or 0) - new_score)
                            if score_diff < 5.0:
                                skipped += 1
                                continue

                        # Update existing
                        existing.composite_quality_score = new_score
                        existing.stars = repo_data.get("stars", 0)
                        existing.open_issues_count = repo_data.get("open_issues_count", 0)
                        existing.last_discovered_at = datetime.now(timezone.utc)
                        existing.metadata = {
                            "language": repo_data.get("language", ""),
                            "topics": repo_data.get("topics", []),
                            "pr_stats": repo_data.get("pr_stats", {}),
                        }
                    else:
                        # Insert new
                        repo = Repository(
                            full_name=full_name,
                            owner=repo_data.get("owner", ""),
                            name=repo_data.get("name", ""),
                            description=repo_data.get("description", ""),
                            stars=repo_data.get("stars", 0),
                            forks_count=repo_data.get("forks_count", 0),
                            open_issues_count=repo_data.get("open_issues_count", 0),
                            language=repo_data.get("language", ""),
                            html_url=repo_data.get("html_url", f"https://github.com/{full_name}"),
                            is_gsoc_org=repo_data.get("is_gsoc_org", False),
                            composite_quality_score=new_score,
                            discovery_source=repo_data.get("source", "unknown"),
                            last_discovered_at=datetime.now(timezone.utc),
                            metadata={
                                "language": repo_data.get("language", ""),
                                "topics": repo_data.get("topics", []),
                                "license": repo_data.get("license", ""),
                                "default_branch": repo_data.get("default_branch", "main"),
                                "pr_stats": repo_data.get("pr_stats", {}),
                            },
                        )
                        session.add(repo)
                    upserted += 1

                except Exception as e:
                    logger.warning(f"Failed to upsert repo {repo_data.get('full_name')}: {e}")
                    continue

            await session.commit()

        logger.info(f"DB upsert: {upserted} upserted, {skipped} skipped")
        return {"upserted_count": upserted, "skipped_count": skipped, "current_step": "upsert_to_db"}

    async def _node_finalize(self, state: RepoDiscoveryState) -> Dict[str, Any]:
        """Finalize and close session."""
        if self.session and not self.session.closed:
            await self.session.close()

        logger.info(
            f"Repo discovery complete: {state['upserted_count']} upserted, "
            f"{state['skipped_count']} skipped, "
            f"sources: {state['sources_crawled']}"
        )
        return {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_step": "complete",
        }

    # ── Helper methods ──────────────────────────────────────────────────────

    async def _get_org_top_repos(self, org: str, gsoc_bonus: bool = False, max_repos: int = 5) -> List[Dict]:
        """Fetch top repos for a GitHub org."""
        repos = []
        try:
            async with self.session.get(
                f"https://api.github.com/orgs/{org}/repos",
                params={"sort": "stars", "direction": "desc", "per_page": max_repos, "type": "public"},
                headers=self.github_headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        repos.append({
                            "full_name": item["full_name"],
                            "owner": item["owner"]["login"],
                            "name": item["name"],
                            "is_gsoc_org": gsoc_bonus,
                            "source": "gsoc_org" if gsoc_bonus else "org_crawl",
                            "stars": item.get("stargazers_count", 0),
                            "language": item.get("language", ""),
                            "description": item.get("description", ""),
                            "open_issues_count": item.get("open_issues_count", 0),
                            "forks_count": item.get("forks_count", 0),
                            "pushed_at": item.get("pushed_at", ""),
                            "html_url": item.get("html_url", ""),
                            "archived": item.get("archived", False),
                        })
        except Exception as e:
            logger.debug(f"Failed to get repos for org {org}: {e}")
        await asyncio.sleep(0.3)
        return [r for r in repos if not r.get("archived")]

    async def _fetch_pr_stats(self, full_name: str) -> Dict[str, Any]:
        """Fetch merged/total PR stats for merge probability scoring."""
        try:
            merged_count = 0
            total_count = 0
            days_to_merge_list = []

            # Get recent PRs
            async with self.session.get(
                f"https://api.github.com/repos/{full_name}/pulls",
                params={"state": "closed", "per_page": 30, "sort": "updated", "direction": "desc"},
                headers=self.github_headers,
            ) as resp:
                if resp.status == 200:
                    prs = await resp.json()
                    for pr in prs:
                        total_count += 1
                        if pr.get("merged_at"):
                            merged_count += 1
                            # Calculate days to merge
                            created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
                            merged = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
                            days = (merged - created).total_seconds() / 86400
                            days_to_merge_list.append(days)

            avg_days = sum(days_to_merge_list) / len(days_to_merge_list) if days_to_merge_list else 30
            merge_rate = merged_count / total_count if total_count > 0 else 0.5

            return {
                "pr_stats": {
                    "merged_prs": merged_count,
                    "total_prs": total_count,
                    "merge_rate": merge_rate,
                    "avg_days_to_merge": avg_days,
                }
            }
        except Exception as e:
            logger.debug(f"PR stats fetch failed for {full_name}: {e}")
            return {"pr_stats": {"merged_prs": 0, "total_prs": 0, "merge_rate": 0.5, "avg_days_to_merge": 30}}

    def _compute_composite_score(self, repo: Dict[str, Any]) -> float:
        """
        Composite quality score (0-100):
        - gsoc_bonus     = 30 if is_gsoc_org
        - responsiveness = 25 * (1 - avg_days_to_merge/30).clip(0,1)
        - stars_momentum = 15 * log(stars + 1) / log(10000)
        - pr_acceptance  = 20 * merge_rate.clip(0,1)
        - issue_activity = 10 * log(open_issues + 1) / log(100)
        """
        pr_stats = repo.get("pr_stats", {})
        stars = repo.get("stars", 0)
        open_issues = repo.get("open_issues_count", 0)
        is_gsoc = repo.get("is_gsoc_org", False)
        avg_days = pr_stats.get("avg_days_to_merge", 30)
        merge_rate = pr_stats.get("merge_rate", 0.5)

        gsoc_bonus = 30.0 if is_gsoc else 0.0
        responsiveness = 25.0 * max(0.0, min(1.0, 1.0 - avg_days / 30.0))
        stars_momentum = 15.0 * math.log(stars + 1) / math.log(10000) if stars > 0 else 0.0
        pr_acceptance = 20.0 * min(1.0, merge_rate)
        issue_activity = 10.0 * math.log(open_issues + 1) / math.log(100) if open_issues > 0 else 0.0

        composite = gsoc_bonus + responsiveness + stars_momentum + pr_acceptance + issue_activity
        return round(min(100.0, composite), 2)
