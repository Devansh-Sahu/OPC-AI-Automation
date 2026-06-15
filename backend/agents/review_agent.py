import logging
from backend.agents.base_agent import BaseAgent
from backend.core.llm import chat_completion

class ReviewAgent(BaseAgent):
    """
    Acts as a Senior Security & Performance Reviewer before a PR is created.
    """
    
    async def run(self, state: dict) -> dict:
        self.logger.info("ReviewAgent performing security and performance analysis...")
        state["current_step"] = "reviewing"
        
        patch_content = state.get("code_changes_patch", "")
        plan = state.get("engineering_plan", {}).get("markdown_content", "")
        
        system_prompt = """You are a Principal Security and Performance Engineer.
        Your job is to review proposed code changes (in Unified Diff format) and identify any:
        1. Security Vulnerabilities (SQLi, XSS, Path Traversal, Hardcoded Secrets)
        2. Performance Bottlenecks (O(N^2) loops, N+1 query problems, Memory Leaks)
        3. Architectural flaws
        
        Output your review in JSON format:
        {
            "approved": boolean,
            "critical_issues": ["list of strings"],
            "major_issues": ["list of strings"],
            "minor_suggestions": ["list of strings"],
            "review_summary": "string"
        }
        """
        
        user_prompt = f"""
Implementation Plan:
{plan}

Proposed Code Changes (Diff):
{patch_content}

Please review the code and provide your JSON assessment.
        """
        
        try:
            response = await chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model="gemini-2.5-flash", # Flash is fast and good enough for basic review formatting
                response_format={"type": "json_object"}
            )
            
            import json
            # Handle potential markdown wrapping around JSON
            content = response.get("content", "{}")
            if content.startswith("```json"):
                content = content.split("```json")[1].rsplit("```", 1)[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].rsplit("```", 1)[0].strip()
                
            review_data = json.loads(content)
            
            state["review_comments"] = review_data
            
            # If critical issues are found, we could loop back to coding, but for now we just flag it
            if not review_data.get("approved", True) and len(review_data.get("critical_issues", [])) > 0:
                self.logger.warning("Review failed due to critical security/performance issues.")
            else:
                self.logger.info("Code review passed.")
                
        except Exception as e:
            self.logger.error(f"Review failed: {e}")
            state["error"] = str(e)
            
        return state
