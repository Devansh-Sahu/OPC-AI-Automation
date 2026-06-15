import logging
from backend.agents.base_agent import BaseAgent
from backend.core.llm import chat_completion

class InnovationAgent(BaseAgent):
    """
    Proactively scans a repository to find feature gaps or architectural debt
    and generates an RFC proposal (INNOVATION tier).
    """
    
    async def run(self, state: dict) -> dict:
        self.logger.info("InnovationAgent scanning repo for architectural improvements...")
        state["current_step"] = "innovating"
        
        repo_analysis = state.get("repo_analysis", {})
        
        system_prompt = """You are a Principal Software Architect.
        Analyze the repository details and suggest one major feature or architectural improvement (RFC).
        Format the output as a Markdown RFC containing:
        - Problem Statement
        - Proposed Solution
        - Technical Design
        - Estimated Effort
        """
        
        user_prompt = f"Repository Architecture & Stats:\n{repo_analysis}\n\nGenerate an RFC proposal."
        
        try:
            response = await chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model="gemini-2.5-flash"
            )
            
            rfc_content = response.get("content", "")
            state["innovation_rfc"] = rfc_content
            self.logger.info("Innovation RFC generated successfully.")
            
        except Exception as e:
            self.logger.error(f"Innovation generation failed: {e}")
            state["error"] = str(e)
            
        return state
