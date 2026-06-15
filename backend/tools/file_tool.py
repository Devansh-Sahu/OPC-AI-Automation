import os
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

class FileTool:
    def __init__(self, workspace_dir: str = "/tmp/repos"):
        self.workspace_dir = Path(workspace_dir)
        
    def _safe_path(self, repo_name: str, file_path: str) -> Path:
        """Ensure path is within the workspace sandbox to prevent path traversal."""
        base_path = (self.workspace_dir / repo_name).resolve()
        full_path = (base_path / file_path).resolve()
        
        if not str(full_path).startswith(str(base_path)):
            raise ValueError(f"Path traversal attempted: {file_path}")
        return full_path

    def read_file(self, repo_name: str, file_path: str) -> str:
        """Read content of a file."""
        safe_path = self._safe_path(repo_name, file_path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()
            
    def write_file(self, repo_name: str, file_path: str, content: str) -> bool:
        """Write content to a file."""
        safe_path = self._safe_path(repo_name, file_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
        
    def list_directory(self, repo_name: str, dir_path: str = ".") -> list[str]:
        """List files in a directory."""
        safe_path = self._safe_path(repo_name, dir_path)
        if not safe_path.exists() or not safe_path.is_dir():
            return []
            
        return [str(p.relative_to(self.workspace_dir / repo_name)) 
                for p in safe_path.iterdir()]
                
    def search_in_files(self, repo_name: str, pattern: str) -> list[str]:
        """Simple regex grep search across the repo."""
        base_path = self._safe_path(repo_name, ".")
        matches = []
        regex = re.compile(pattern)
        
        for root, _, files in os.walk(base_path):
            if '.git' in root or 'node_modules' in root:
                continue
                
            for file in files:
                filepath = Path(root) / file
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = str(filepath.relative_to(base_path))
                                matches.append(f"{rel_path}:{line_num}:{line.strip()}")
                except UnicodeDecodeError:
                    pass # Skip binary files
        return matches[:50] # Limit results

file_tool = FileTool()
