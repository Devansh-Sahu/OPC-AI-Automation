import os
import logging
from git import Repo, GitCommandError
from pathlib import Path

logger = logging.getLogger(__name__)

class GitTool:
    def __init__(self, workspace_dir: str = "/tmp/repos"):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
    def clone_repo(self, url: str, name: str, depth: int = 1) -> str:
        """Clone a repository into the workspace."""
        repo_path = self.workspace_dir / name
        if repo_path.exists():
            logger.info(f"Repo {name} already exists at {repo_path}")
            return str(repo_path)
            
        try:
            logger.info(f"Cloning {url} into {repo_path}...")
            Repo.clone_from(url, repo_path, depth=depth)
            return str(repo_path)
        except GitCommandError as e:
            logger.error(f"Failed to clone repo: {e}")
            raise
            
    def create_branch(self, repo_path: str, branch_name: str) -> bool:
        """Create and checkout a new branch."""
        try:
            repo = Repo(repo_path)
            new_branch = repo.create_head(branch_name)
            new_branch.checkout()
            logger.info(f"Created and checked out branch {branch_name}")
            return True
        except GitCommandError as e:
            logger.error(f"Failed to create branch: {e}")
            return False
            
    def commit_changes(self, repo_path: str, message: str) -> bool:
        """Stage all changes and commit."""
        try:
            repo = Repo(repo_path)
            repo.git.add(A=True)
            repo.index.commit(message)
            logger.info(f"Committed changes with message: {message}")
            return True
        except GitCommandError as e:
            logger.error(f"Failed to commit changes: {e}")
            return False
            
    def get_diff(self, repo_path: str) -> str:
        """Get the current unified diff."""
        try:
            repo = Repo(repo_path)
            return repo.git.diff('HEAD')
        except GitCommandError as e:
            logger.error(f"Failed to get diff: {e}")
            return ""

git_tool = GitTool()
