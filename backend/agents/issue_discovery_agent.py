"""
Issue Discovery Agent - Scans repos for senior/staff/innovation-level issues.
Skips beginner issues entirely. Uses XGBoost scoring for merge probability.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, TypedDict

import aiohttp
import numpy as np
from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent, BaseAgentState
from backend.core.config import settings
from backend.core.database import async_session

logger = logging.getLogger(__name__)

# Labels to explicitly FILTER OUT (beginner/easy)
EXCLUDE_LABELS = {
    "good first issue", "good-first-issue", "beginner", "beginner-friendly",
    "easy", "easy-pick", "starter", "newbie", "first-timers-only",
    "help wanted easy", "documentation", "docs", "typo", "trivial",
    "low priority", "wontfix", "invalid", "duplicate",
}

# Labels to PREFER (senior/complex)
TARGET_LABELS = {
    "performance", "security", "vulnerability", "cve", "regression",
    "critical", "memory-leak", "race-condition", "architecture",
    "data-loss", "corruption", "deadlock", "oom", "out-of-memory",
    "enhancement", "feature", "rfc", "design", "breaking-change",
    "distributed", "scalability", "reliability", "observability",
}

COMPLEXITY_TIER_INNOVATION = "INNOVATION"
COMPLEXITY_TIER_STAFF = "STAFF"
COMPLEXITY_TIER_SENIOR = "SENIOR"


class IssueDiscoveryState(BaseAgentState):
    repositories: List[Dict[str, Any]]
    current_repo_index: int
    discovered_issues: List[Dict[str, Any]]
    scored_issues: List[Dict[str, Any]]
    total_repos_scanned: int
    total_issues_found: int


class IssueDiscoveryAgent(BaseAgent):
    """
    Scans all repositories for senior-level issues worth solving autonomously.
    Scores each issue by complexity and merge probability, stores to DB.
    """

    def __init__(self):
        super().__init__("issue_discovery_agent")
        self.github_headers = {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.session: Optional[aiohttp.ClientSession] = None
        self._xgb_model = None
        self._load_xgb_model()

    def _load_xgb_model(self):
        """Load XGBoost model if available, fall back to heuristics."""
        try:
            import xgboost as xgb
            import os
            model_path = settings.XGBOOST_MODEL_PATH if hasattr(settings, "XGBOOST_MODEL_PATH") else "models/merge_probability.json"
            if os.path.exists(model_path):
                self._xgb_model = xgb.Booster()
                self._xgb_model.load_model(model_path)
                logger.info("XGBoost merge probability model loaded")
        except Exception as e:
            logger.info(f"XGBoost not available, using heuristic scoring: {e}")

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(IssueDiscoveryState)

        graph.add_node("load_repositories", self._node_load_repositories)
        graph.add_node("scan_issues", self._node_scan_issues)
        graph.add_node("score_issues", self._node_score_issues)
        graph.add_node("upsert_issues", self._node_upsert_issues)
        graph.add_node("finalize", self._node_finalize)

        graph.set_entry_point("load_repositories")
        graph.add_edge("load_repositories", "scan_issues")
        graph.add_edge("scan_issues", "score_issues")
        graph.add_edge("score_issues", "upsert_issues")
        graph.add_edge("upsert_issues", "finalize")
        graph.add_edge("finalize", END)

        return graph

    async def run(
        self, input_data: Optional[Dict[str, Any]] = None, run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        run_id = run_id or self._new_run_id()
        self._create_context(run_id)

        # Allow filtering to specific repos
        repo_ids = (input_data or {}).get("repo_ids", [])

        initial_state: IssueDiscoveryState = {
            **self._base_initial_state(run_id),
            "repositories": [],
            "current_repo_index": 0,
            "discovered_issues": [],
            "scored_issues": [],
            "total_repos_scanned": 0,
            "total_issues_found": 0,
            "metadata": {"repo_ids_filter": repo_ids},
        }

        config = {"configurable": {"thread_id": run_id}}
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "OpenSourceAIEngineer/1.0"},
        )

        try:
            final_state = await self.compiled_graph.ainvoke(initial_state, config=config)
            return final_state
        finally:
            if self.session and not self.session.closed:
                await self.session.close()

    async def _node_load_repositories(self, state: IssueDiscoveryState) -> Dict[str, Any]:
        """Load active repos from DB ordered by quality score."""
        async with async_session() as session:
            from backend.models.repository import Repository
            from sqlalchemy import select

            query = (
                select(Repository)
                .where(Repository.is_active == True)
                .order_by(Repository.composite_quality_score.desc())
                .limit(200)
            )

            repo_ids_filter = state["metadata"].get("repo_ids_filter", [])
            if repo_ids_filter:
                query = query.where(Repository.id.in_(repo_ids_filter))

            result = await session.execute(query)
            repos = result.scalars().all()

            repo_list = [
                {
                    "id": str(r.id),
                    "full_name": r.full_name,
                    "owner": r.owner,
                    "name": r.name,
                    "composite_quality_score": float(r.composite_quality_score or 0),
                    "stars": r.stars or 0,
                    "language": r.language or "",
                    "metadata": r.metadata or {},
                }
                for r in repos
            ]

        logger.info(f"Loaded {len(repo_list)} repos to scan")
        return {"repositories": repo_list, "current_step": "load_repositories"}

    async def _node_scan_issues(self, state: IssueDiscoveryState) -> Dict[str, Any]:
        """Scan each repo for qualifying senior-level issues."""
        repos = state["repositories"]
        all_issues = []

        semaphore = asyncio.Semaphore(5)  # 5 concurrent repo scans

        async def scan_repo(repo: Dict) -> List[Dict]:
            async with semaphore:
                return await self._scan_single_repo(repo)

        tasks = [scan_repo(r) for r in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for repo, result in zip(repos, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to scan {repo['full_name']}: {result}")
            elif result:
                all_issues.extend(result)

        logger.info(f"Total qualifying issues found: {len(all_issues)}")
        return {
            "discovered_issues": all_issues,
            "total_repos_scanned": len(repos),
            "total_issues_found": len(all_issues),
            "current_step": "scan_issues",
        }

    async def _scan_single_repo(self, repo: Dict) -> List[Dict]:
        """Scan a single repo for senior issues."""
        full_name = repo["full_name"]
        qualifying = []

        try:
            # Fetch open issues (not PRs)
            page = 1
            while page <= 3:  # Max 3 pages = 90 issues
                async with self.session.get(
                    f"https://api.github.com/repos/{full_name}/issues",
                    params={
                        "state": "open",
                        "sort": "updated",
                        "direction": "desc",
                        "per_page": 30,
                        "page": page,
                    },
                    headers=self.github_headers,
                ) as resp:
                    if resp.status != 200:
                        break
                    issues = await resp.json()
                    if not issues:
                        break

                    for issue in issues:
                        # Skip PRs (GitHub returns them in issues endpoint too)
                        if "pull_request" in issue:
                            continue

                        qualified = await self._qualify_issue(issue, repo)
                        if qualified:
                            qualifying.append(qualified)

                    page += 1
                    await asyncio.sleep(0.5)

        except Exception as e:
            logger.warning(f"Error scanning {full_name}: {e}")

        return qualifying

    async def _qualify_issue(self, issue: Dict, repo: Dict) -> Optional[Dict]:
        """
        Apply qualification filters to determine if issue is worth solving.
        Returns enriched issue dict or None if filtered out.
        """
        issue_labels = {l["name"].lower() for l in issue.get("labels", [])}

        # 1. Filter OUT beginner labels
        if issue_labels & EXCLUDE_LABELS:
            return None

        # 2. Check for existing open PRs on this issue
        if issue.get("comments", 0) > 0:
            has_pr = await self._check_issue_has_open_pr(
                repo["full_name"], issue["number"]
            )
            if has_pr:
                return None

        # 3. Skip issues inactive > 180 days
        updated_at_str = issue.get("updated_at", "")
        if updated_at_str:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - updated_at).days
            if age_days > 180:
                return None

        # 4. Classify complexity tier
        tier = self._classify_tier(issue, issue_labels)
        if tier is None:
            return None  # Skip JUNIOR issues

        # 5. Extract technical features
        body = issue.get("body", "") or ""
        features = self._extract_features(issue, body, issue_labels)

        return {
            "id": str(issue["id"]),
            "number": issue["number"],
            "title": issue["title"],
            "body": body[:5000],  # Truncate for storage
            "html_url": issue["html_url"],
            "repo_full_name": repo["full_name"],
            "repo_id": repo["id"],
            "repo_quality_score": repo["composite_quality_score"],
            "labels": list(issue_labels),
            "comments": issue.get("comments", 0),
            "complexity_tier": tier,
            "created_at": issue.get("created_at", ""),
            "updated_at": issue.get("updated_at", ""),
            "user_login": (issue.get("user") or {}).get("login", ""),
            "features": features,
            "milestone": (issue.get("milestone") or {}).get("title", ""),
            "assignees": [a["login"] for a in issue.get("assignees", [])],
        }

    def _classify_tier(self, issue: Dict, labels: set) -> Optional[str]:
        """
        Classify issue into INNOVATION / STAFF / SENIOR, or None (skip).
        """
        title = issue.get("title", "").lower()
        body = (issue.get("body", "") or "").lower()
        text = title + " " + body

        # INNOVATION: AI enhancement, RFC, new feature with design doc
        innovation_signals = [
            "rfc:", "rfc -", "proposal:", "design doc", "feature request",
            "add support for", "implement", "ai enhancement", "ml", "llm",
            "new algorithm", "roadmap", "vision",
        ]
        innovation_labels = {"rfc", "proposal", "enhancement", "feature", "design"}
        if any(s in text for s in innovation_signals) and (labels & innovation_labels):
            return COMPLEXITY_TIER_INNOVATION

        # STAFF: security, data consistency, distributed systems
        staff_signals = [
            "security", "vulnerability", "cve-", "sql injection", "xss",
            "csrf", "authentication", "authorization", "cryptograph",
            "data corruption", "data loss", "consistency", "distributed",
            "consensus", "partition tolerance", "byzantine", "race condition",
            "deadlock", "livelock", "algorithm complexity",
        ]
        staff_labels = {"security", "vulnerability", "cve", "data-loss", "critical", "race-condition"}
        if any(s in text for s in staff_signals) or (labels & staff_labels):
            return COMPLEXITY_TIER_STAFF

        # SENIOR: performance regression, memory leak, OOM, architectural debt
        senior_signals = [
            "performance", "regression", "memory leak", "oom", "out of memory",
            "cpu usage", "high latency", "slow", "bottleneck", "profil",
            "benchmark", "degradation", "throughput", "architectural",
            "refactor", "technical debt", "scalab", "concurrency",
        ]
        senior_labels = {
            "performance", "regression", "memory-leak", "oom", "architecture",
            "refactor", "scalability", "bug",
        }
        if any(s in text for s in senior_signals) or (labels & senior_labels):
            return COMPLEXITY_TIER_SENIOR

        # Check for general complexity indicators even without matching labels
        body_text = issue.get("body", "") or ""
        has_stack_trace = bool(re.search(r"traceback|stack trace|exception|error at line", body_text, re.I))
        has_benchmarks = bool(re.search(r"benchmark|ns/op|ms/op|throughput|latency", body_text, re.I))
        has_code = bool(re.search(r"```", body_text))
        body_long = len(body_text) > 800

        if sum([has_stack_trace, has_benchmarks, has_code, body_long]) >= 2:
            return COMPLEXITY_TIER_SENIOR

        return None  # Skip this issue

    def _extract_features(self, issue: Dict, body: str, labels: set) -> Dict[str, Any]:
        """Extract ML features for XGBoost scoring."""
        has_stack_trace = bool(re.search(r"traceback|stack trace|at \w+\.py", body, re.I))
        has_benchmark = bool(re.search(r"benchmark|ns/op|ms/op|throughput", body, re.I))
        has_code_block = "```" in body
        linked_files = len(re.findall(r"`[\w/.-]+\.(py|js|ts|go|rs|java|cpp)`", body))
        discussion_thread_length = issue.get("comments", 0)
        body_length = len(body)

        label_severity = 0
        if labels & {"security", "vulnerability", "cve"}:
            label_severity = 5
        elif labels & {"critical", "regression", "data-loss"}:
            label_severity = 4
        elif labels & {"performance", "memory-leak", "oom"}:
            label_severity = 3
        elif labels & {"enhancement", "architecture"}:
            label_severity = 2
        else:
            label_severity = 1

        return {
            "body_length": body_length,
            "body_length_gt_500": int(body_length > 500),
            "has_stack_trace": int(has_stack_trace),
            "has_benchmark": int(has_benchmark),
            "has_code_block": int(has_code_block),
            "linked_files_count": linked_files,
            "discussion_length": discussion_thread_length,
            "discussion_gt_5": int(discussion_thread_length > 5),
            "label_severity": label_severity,
            "has_milestone": int(bool(issue.get("milestone"))),
            "assignee_count": len(issue.get("assignees", [])),
        }

    async def _node_score_issues(self, state: IssueDiscoveryState) -> Dict[str, Any]:
        """Score each issue with complexity + merge probability + repo quality."""
        issues = state["discovered_issues"]
        scored = []

        for issue in issues:
            features = issue.get("features", {})
            tier = issue.get("complexity_tier", COMPLEXITY_TIER_SENIOR)

            # Complexity score (0-100)
            complexity_score = self._compute_complexity_score(features, tier)

            # Merge probability (0-100)
            merge_prob = self._compute_merge_probability(features, issue)

            # Repo quality (0-100)
            repo_quality = min(100.0, issue.get("repo_quality_score", 50.0))

            # Composite score
            composite = (complexity_score * 0.4) + (merge_prob * 0.4) + (repo_quality * 0.2)

            scored.append({
                **issue,
                "complexity_score": round(complexity_score, 2),
                "merge_probability": round(merge_prob, 2),
                "composite_score": round(composite, 2),
            })

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        logger.info(f"Scored {len(scored)} issues")
        return {"scored_issues": scored, "current_step": "score_issues"}

    def _compute_complexity_score(self, features: Dict, tier: str) -> float:
        """Heuristic complexity score 0-100."""
        base = {"INNOVATION": 80, "STAFF": 70, "SENIOR": 55}.get(tier, 50)

        bonus = 0
        bonus += min(20, features.get("body_length", 0) / 100)
        bonus += features.get("has_stack_trace", 0) * 5
        bonus += features.get("has_benchmark", 0) * 8
        bonus += features.get("has_code_block", 0) * 3
        bonus += min(10, features.get("linked_files_count", 0) * 2)
        bonus += min(10, features.get("discussion_length", 0) * 0.5)
        bonus += features.get("label_severity", 1) * 2

        return min(100.0, base + bonus)

    def _compute_merge_probability(self, features: Dict, issue: Dict) -> float:
        """Compute merge probability using XGBoost if available, else heuristic."""
        if self._xgb_model:
            try:
                import xgboost as xgb
                feature_vector = np.array([[
                    features.get("body_length_gt_500", 0),
                    features.get("has_stack_trace", 0),
                    features.get("has_benchmark", 0),
                    features.get("has_code_block", 0),
                    features.get("linked_files_count", 0),
                    features.get("discussion_gt_5", 0),
                    features.get("label_severity", 1),
                    features.get("has_milestone", 0),
                    issue.get("repo_quality_score", 50) / 100,
                ]], dtype=np.float32)
                dmatrix = xgb.DMatrix(feature_vector)
                prob = float(self._xgb_model.predict(dmatrix)[0])
                return min(100.0, max(0.0, prob * 100))
            except Exception as e:
                logger.debug(f"XGBoost prediction failed: {e}")

        # Heuristic fallback
        score = 40.0  # base
        score += features.get("has_stack_trace", 0) * 10
        score += features.get("has_benchmark", 0) * 8
        score += features.get("discussion_gt_5", 0) * 8
        score += (features.get("label_severity", 1) - 1) * 5
        score += features.get("body_length_gt_500", 0) * 5
        score += features.get("has_milestone", 0) * 7
        score -= features.get("assignee_count", 0) * 10  # Already assigned = lower chance

        return min(100.0, max(0.0, score))

    async def _check_issue_has_open_pr(self, full_name: str, issue_number: int) -> bool:
        """Check if an issue already has an associated open PR."""
        try:
            async with self.session.get(
                f"https://api.github.com/repos/{full_name}/issues/{issue_number}/timeline",
                headers={**self.github_headers, "Accept": "application/vnd.github.mockingbird-preview+json"},
            ) as resp:
                if resp.status == 200:
                    events = await resp.json()
                    for event in events:
                        if event.get("event") == "cross-referenced":
                            source = event.get("source", {})
                            if source.get("type") == "pull_request":
                                pr_state = (source.get("issue") or {}).get("state", "")
                                if pr_state == "open":
                                    return True
        except Exception:
            pass
        return False

    async def _node_upsert_issues(self, state: IssueDiscoveryState) -> Dict[str, Any]:
        """Upsert scored issues into the issues table."""
        issues = state["scored_issues"]
        upserted = 0

        async with async_session() as session:
            from backend.models.issue import Issue
            from sqlalchemy import select

            for issue_data in issues[:300]:  # Cap at top 300
                try:
                    result = await session.execute(
                        select(Issue).where(
                            Issue.github_issue_id == issue_data["id"]
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.composite_score = issue_data["composite_score"]
                        existing.complexity_score = issue_data["complexity_score"]
                        existing.merge_probability = issue_data["merge_probability"]
                        existing.complexity_tier = issue_data["complexity_tier"]
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        new_issue = Issue(
                            github_issue_id=issue_data["id"],
                            number=issue_data["number"],
                            title=issue_data["title"],
                            body=issue_data["body"],
                            html_url=issue_data["html_url"],
                            repo_full_name=issue_data["repo_full_name"],
                            labels=issue_data["labels"],
                            complexity_tier=issue_data["complexity_tier"],
                            complexity_score=issue_data["complexity_score"],
                            merge_probability=issue_data["merge_probability"],
                            composite_score=issue_data["composite_score"],
                            status="discovered",
                            features=issue_data["features"],
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                            github_created_at=issue_data.get("created_at"),
                            github_updated_at=issue_data.get("updated_at"),
                        )
                        session.add(new_issue)
                    upserted += 1
                except Exception as e:
                    logger.warning(f"Failed to upsert issue {issue_data.get('number')}: {e}")

            await session.commit()

        logger.info(f"Upserted {upserted} issues to DB")
        return {"current_step": "upsert_issues"}

    async def _node_finalize(self, state: IssueDiscoveryState) -> Dict[str, Any]:
        logger.info(
            f"Issue discovery complete: scanned {state['total_repos_scanned']} repos, "
            f"found {state['total_issues_found']} qualifying issues"
        )
        return {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_step": "complete",
        }
