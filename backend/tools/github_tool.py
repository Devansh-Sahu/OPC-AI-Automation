import logging
from backend.services.github_service import github_service

logger = logging.getLogger(__name__)

class GitHubTool:
    """Wrapper around GitHubService designed to be passed to LLM agents as a Tool."""
    
    def get_issue_detail(self, owner: str, repo_name: str, issue_number: int) -> dict:
        try:
            repo = github_service.get_repo(owner, repo_name)
            issue = repo.get_issue(issue_number)
            return {
                "title": issue.title,
                "body": issue.body,
                "labels": [l.name for l in issue.labels],
                "state": issue.state,
                "comments": [c.body for c in issue.get_comments()]
            }
        except Exception as e:
            logger.error(f"Error fetching issue {issue_number}: {e}")
            return {"error": str(e)}
            
    def create_pull_request(self, owner: str, repo_name: str, title: str, body: str, head: str) -> dict:
        try:
            repo = github_service.get_repo(owner, repo_name)
            pr = github_service.create_draft_pr(repo, title, body, head)
            return {"url": pr.html_url, "number": pr.number}
        except Exception as e:
            return {"error": str(e)}

github_tool = GitHubTool()
