import logging
import httpx
from datetime import datetime, timezone
from backend.core.config import settings

logger = logging.getLogger(__name__)

class RepoDiscoveryService:
    def __init__(self):
        self.KNOWN_GSOC_ORGS = [
            "kubernetes", "prometheus", "grafana", "django", "flask", 
            "pytorch", "tensorflow", "sympy", "numpy", "scipy", 
            "matplotlib", "pandas", "jupyter", "apache", "mozilla", 
            "gnome", "kde", "openmrs", "fossasia", "cncf"
        ]
        
    async def discover_from_gsoc(self) -> list[dict]:
        """Fetch repositories from known GSoC organizations using GitHub API."""
        repos = []
        if not settings.GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN not set. Skipping discovery.")
            return repos
            
        headers = {
            "Authorization": f"token {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with httpx.AsyncClient() as client:
            for org in self.KNOWN_GSOC_ORGS:
                try:
                    response = await client.get(f"https://api.github.com/orgs/{org}/repos?type=public&per_page=10&sort=pushed", headers=headers)
                    if response.status_code == 200:
                        org_repos = response.json()
                        for r in org_repos:
                            repos.append({
                                "github_url": r["html_url"],
                                "name": r["name"],
                                "owner": org,
                                "description": r.get("description"),
                                "language": r.get("language"),
                                "stars": r.get("stargazers_count", 0),
                                "forks": r.get("forks_count", 0),
                                "open_issues_count": r.get("open_issues_count", 0),
                                "gsoc_history": True,
                                "foundation_type": "GSOC",
                                "is_active": True
                            })
                except Exception as e:
                    logger.error(f"Error fetching repos for {org}: {e}")
                    
        return repos

    async def score_repo(self, repo_data: dict) -> float:
        """Calculate a composite quality score for a repository."""
        score = 0.0
        
        # Base stars
        stars = repo_data.get("stars", 0)
        if stars > 10000: score += 30
        elif stars > 1000: score += 20
        elif stars > 100: score += 10
            
        # Foundation bonus
        if repo_data.get("gsoc_history"): score += 25
        if repo_data.get("foundation_type") in ["CNCF", "Apache", "Linux"]: score += 30
            
        # Activity bonus (proxy via open issues for now)
        issues = repo_data.get("open_issues_count", 0)
        if 50 < issues < 500: score += 15
            
        return min(100.0, score)

repo_discovery_service = RepoDiscoveryService()
