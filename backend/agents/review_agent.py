from .base_agent import BaseAgent
from backend.models import AgentRun

class ReviewAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("ReviewAgent running...")
        state["current_step"] = "reviewing"
        return state
