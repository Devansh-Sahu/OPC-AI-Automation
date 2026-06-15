from .base_agent import BaseAgent
from backend.models import AgentRun

class InnovationAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("InnovationAgent running...")
        state["current_step"] = "innovating"
        return state
