import logging
from pathlib import Path
# tree_sitter would be used here, but we'll mock it for now since building grammars
# in the current env might be tricky without gcc available for all languages.

logger = logging.getLogger(__name__)

class CodeAnalysisTool:
    def chunk_file(self, file_path: str, language: str = None) -> list[dict]:
        """
        Parses a file and returns AST-based chunks.
        MOCKED: Returns naive line-based chunks for now until tree-sitter is compiled.
        """
        chunks = []
        path = Path(file_path)
        if not path.exists():
            return chunks
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Naive chunking (every 50 lines)
            lines = content.split('\n')
            for i in range(0, len(lines), 50):
                chunk_lines = lines[i:i+50]
                chunks.append({
                    "type": "block",
                    "file_path": str(path),
                    "start_line": i + 1,
                    "end_line": i + len(chunk_lines),
                    "content": '\n'.join(chunk_lines)
                })
        except Exception as e:
            logger.error(f"Failed to chunk file {file_path}: {e}")
            
        return chunks
        
    def detect_language(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        if ext == '.py': return 'python'
        if ext in ['.js', '.jsx']: return 'javascript'
        if ext in ['.ts', '.tsx']: return 'typescript'
        if ext == '.go': return 'go'
        if ext == '.rs': return 'rust'
        if ext == '.java': return 'java'
        return 'unknown'

code_analysis_tool = CodeAnalysisTool()
