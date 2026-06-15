from .base_agent import BaseAgent
from backend.models import AgentRun

class PRAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("PRAgent running...")
        state["current_step"] = "creating_pr"
        return state
