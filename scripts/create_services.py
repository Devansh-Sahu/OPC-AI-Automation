import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\devansh\OneDrive\Desktop\Open Source Engineer\backend")

# API routes
webhooks_py = """from fastapi import APIRouter
router = APIRouter()

@router.post("/")
async def receive_webhook():
    return {"status": "ok"}
"""

feedback_py = """from fastapi import APIRouter
router = APIRouter()

@router.get("/")
async def get_feedback():
    return {"data": []}
"""

websocket_py = """from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
"""

# Services
services_init = """from .cost_tracker import CostTracker
from .secrets_manager import SecretsManager
from .github_service import GitHubService
from .merge_predictor import MergePredictor
from .repo_discovery_service import RepoDiscoveryService
from .issue_scorer import IssueScorer
from .context_manager import ContextManager

__all__ = [
    "CostTracker", "SecretsManager", "GitHubService", "MergePredictor",
    "RepoDiscoveryService", "IssueScorer", "ContextManager"
]
"""

cost_tracker_py = """class CostTracker:
    def get_total_cost(self): return 0.0
"""
secrets_manager_py = """class SecretsManager:
    def get_secret(self, key): return "secret"
"""
github_service_py = """class GitHubService:
    def get_repo(self, name): return {}
"""
merge_predictor_py = """class MergePredictor:
    def predict(self, features): return 0.5
"""
repo_discovery_service_py = """class RepoDiscoveryService:
    def discover(self): return []
"""
issue_scorer_py = """class IssueScorer:
    def score(self, issue): return 0.5
"""
context_manager_py = """class ContextManager:
    def compress(self, context): return context
"""

# Tools
tools_init = """from .github_tool import GitHubTool
from .git_tool import GitTool
from .code_analysis_tool import CodeAnalysisTool
from .file_tool import FileTool

__all__ = ["GitHubTool", "GitTool", "CodeAnalysisTool", "FileTool"]
"""

github_tool_py = """class GitHubTool:
    def run(self): pass
"""
git_tool_py = """class GitTool:
    def run(self): pass
"""
code_analysis_tool_py = """class CodeAnalysisTool:
    def run(self): pass
"""
file_tool_py = """class FileTool:
    def run(self): pass
"""

files = {
    "api/routes/webhooks.py": webhooks_py,
    "api/routes/feedback.py": feedback_py,
    "api/websocket.py": websocket_py,
    "services/__init__.py": services_init,
    "services/cost_tracker.py": cost_tracker_py,
    "services/secrets_manager.py": secrets_manager_py,
    "services/github_service.py": github_service_py,
    "services/merge_predictor.py": merge_predictor_py,
    "services/repo_discovery_service.py": repo_discovery_service_py,
    "services/issue_scorer.py": issue_scorer_py,
    "services/context_manager.py": context_manager_py,
    "tools/__init__.py": tools_init,
    "tools/github_tool.py": github_tool_py,
    "tools/git_tool.py": git_tool_py,
    "tools/code_analysis_tool.py": code_analysis_tool_py,
    "tools/file_tool.py": file_tool_py
}

def write_file(path, content):
    with open(BASE_DIR / path, 'w', encoding='utf-8') as f:
        f.write(content)

for path, content in files.items():
    write_file(path, content)
