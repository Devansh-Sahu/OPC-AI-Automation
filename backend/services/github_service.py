import logging
from github import Github, Auth
from github.GithubException import GithubException
from backend.core.config import settings

logger = logging.getLogger(__name__)

class GitHubService:
    def __init__(self):
        if settings.GITHUB_TOKEN:
            auth = Auth.Token(settings.GITHUB_TOKEN)
            self.g = Github(auth=auth)
        else:
            logger.warning("GITHUB_TOKEN not configured. GitHubService will fail on auth-required endpoints.")
            self.g = Github()
            
    def get_repo(self, owner: str, name: str):
        try:
            return self.g.get_repo(f"{owner}/{name}")
        except GithubException as e:
            logger.error(f"Failed to fetch repo {owner}/{name}: {e}")
            raise
            
    def get_open_issues(self, repo_obj, labels: list[str] = None):
        """Fetch open issues, optionally filtered by labels."""
        kwargs = {"state": "open"}
        if labels:
            # PyGithub requires Label objects or strings depending on version, usually strings work
            kwargs["labels"] = labels
            
        try:
            return list(repo_obj.get_issues(**kwargs)[:20]) # Limit for cost
        except GithubException as e:
            logger.error(f"Failed to fetch issues: {e}")
            return []

    def create_draft_pr(self, repo_obj, title: str, body: str, head_branch: str, base_branch: str = "main"):
        """Create a Draft PR."""
        try:
            pr = repo_obj.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch,
                draft=True
            )
            logger.info(f"Created draft PR: {pr.html_url}")
            return pr
        except GithubException as e:
            logger.error(f"Failed to create PR: {e}")
            raise

github_service = GitHubService()
