import logging
import json

logger = logging.getLogger(__name__)

class ContextManager:
    def __init__(self):
        self.MAX_CONTEXT_TOKENS = 30000 # Keep it safe for 128k models, leaving room for generation
        
    def compress_code_context(self, chunks: list[dict], max_tokens: int = 8000) -> list[dict]:
        """
        Takes a list of retrieved AST chunks and compresses/filters them to fit within token limits.
        Prioritizes chunks with higher semantic relevance.
        """
        # For now, a simple heuristic: take the top N chunks until we hit the char limit approx
        # Assuming 1 token ~= 4 characters
        max_chars = max_tokens * 4
        
        compressed = []
        current_chars = 0
        
        for chunk in chunks:
            chunk_content = chunk.get("content", "")
            chunk_len = len(chunk_content)
            
            if current_chars + chunk_len > max_chars:
                # If we're hitting the limit, we might truncate the last chunk or just stop
                continue
                
            compressed.append(chunk)
            current_chars += chunk_len
            
        logger.info(f"Compressed {len(chunks)} chunks down to {len(compressed)} chunks.")
        return compressed
        
    def build_system_prompt(self, repo_analysis: dict, issue: dict, plan: dict = None) -> str:
        """Constructs the optimal system prompt incorporating repository rules and architecture."""
        
        prompt = "You are a Staff Software Engineer fixing an issue.\n\n"
        
        if repo_analysis:
            prompt += f"Repository Architecture: {repo_analysis.get('architecture_pattern', 'Unknown')}\n"
            prompt += f"Primary Language: {repo_analysis.get('language', 'Unknown')}\n\n"
            
        prompt += f"Issue to fix:\nTITLE: {issue.get('title')}\nBODY:\n{issue.get('body')}\n\n"
        
        if plan:
            prompt += f"Implementation Plan to follow:\n{json.dumps(plan, indent=2)}\n\n"
            
        return prompt

context_manager = ContextManager()
