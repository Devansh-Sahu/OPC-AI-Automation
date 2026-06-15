import logging
from backend.agents.base_agent import BaseAgent
from backend.core.llm import chat_completion

class PlanningAgent(BaseAgent):
    """
    Analyzes the issue and retrieved code to generate a Staff-level implementation plan.
    """
    
    async def run(self, state: dict) -> dict:
        self.logger.info("PlanningAgent analyzing issue and generating RFC-style plan...")
        state["current_step"] = "planning"
        
        repo_analysis = state.get("repo_analysis", {})
        code_chunks = state.get("code_chunks", [])
        issue_details = state.get("issue_details", {"title": "Unknown", "body": ""})
        
        # Build prompt context from chunks
        context_str = ""
        for chunk in code_chunks:
            context_str += f"\n--- File: {chunk.get('file_path')} ---\n{chunk.get('content')}\n"
            
        system_prompt = f"""You are a Staff Software Engineer architecting a solution for a complex issue.
        
Repository Context:
Language: {repo_analysis.get('language', 'Unknown')}
Framework: {repo_analysis.get('framework', 'Unknown')}
Architecture: {repo_analysis.get('architecture_pattern', 'Unknown')}

Your goal is to write a detailed, bulletproof engineering implementation plan.
Do NOT write the actual code files yet. Write the blueprint.
        """
        
        user_prompt = f"""
Issue Title: {issue_details.get('title')}
Issue Body: {issue_details.get('body')}

Relevant Source Code Chunks retrieved:
{context_str}

Please generate a comprehensive Implementation Plan in Markdown format. It MUST include:
1. Root Cause Analysis (Why is this happening/needed?)
2. Architectural Impact (What systems are affected?)
3. Step-by-Step Implementation Strategy (Be specific about file paths and functions to modify)
4. Alternative Approaches Considered (And why you rejected them)
5. Testing Strategy (What specific edge cases must be tested?)
6. Risk Assessment (Could this break backward compatibility or cause regressions?)
        """
        
        try:
            # We enforce a strong model here due to the complexity required
            response = await chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model="qwen3:14b", # Defaulting to local model per project constraints
                fallback_model="gemini-2.5-flash"
            )
            
            plan_content = response.get("content", "")
            
            # Save the plan to state
            state["engineering_plan"] = {
                "markdown_content": plan_content,
                "status": "completed"
            }
            
            self.logger.info("Planning complete. Engineering plan generated.")
            
        except Exception as e:
            self.logger.error(f"Planning failed: {e}")
            state["error"] = str(e)
            
        return state
