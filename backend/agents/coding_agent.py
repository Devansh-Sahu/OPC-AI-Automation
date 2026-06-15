import logging
import json
from backend.agents.base_agent import BaseAgent
from backend.core.llm import chat_completion
from backend.core.sandbox import Sandbox

class CodingAgent(BaseAgent):
    """
    Takes the Implementation Plan and modifies code inside a Docker Sandbox.
    """
    
    async def run(self, state: dict) -> dict:
        self.logger.info("CodingAgent spinning up sandbox and generating code changes...")
        state["current_step"] = "coding"
        
        plan = state.get("engineering_plan", {}).get("markdown_content", "")
        repo_id = state.get("repo_id")
        issue_id = state.get("issue_id")
        
        # In a full implementation, we'd clone the repo into the sandbox volume here.
        # For this prototype, we assume the repo is already in /tmp/repos/{repo_id}
        
        system_prompt = """You are a Staff-level AI Coding Agent. 
You are given an Implementation Plan. Your job is to output the EXACT code changes needed in Unified Diff Patch format.
Do NOT output anything other than the raw patch file. No markdown backticks, no explanations. Just the patch.
        """
        
        user_prompt = f"""
Implementation Plan:
{plan}

Please generate the unified diff patch that applies these changes to the codebase.
        """
        
        try:
            # We enforce a strong model here due to the complexity required for code generation
            response = await chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model="qwen3:14b",
                fallback_model="gemini-2.5-flash"
            )
            
            patch_content = response.get("content", "")
            
            # Clean up potential markdown formatting if the LLM disobeyed
            if patch_content.startswith("```diff"):
                patch_content = patch_content.split("```diff")[1].rsplit("```", 1)[0].strip()
            elif patch_content.startswith("```"):
                patch_content = patch_content.split("```")[1].rsplit("```", 1)[0].strip()
                
            # Save the patch to state
            state["code_changes_patch"] = patch_content
            
            # Here we would normally spin up the Sandbox and apply the patch using `patch -p1 < changes.patch`
            # Sandbox logic omitted for brevity, but the architecture supports it.
            
            self.logger.info("Coding complete. Unified diff generated.")
            
        except Exception as e:
            self.logger.error(f"Coding failed: {e}")
            state["error"] = str(e)
            
        return state
